# diary_bot.py
import os
import glob
from dataclasses import dataclass
from datetime import datetime
from typing import List
import requests
import json

# ===================== 数据结构 =====================

@dataclass
class DiaryEntry:
    date: datetime
    text: str
    path: str


# ===================== 加载日记 =====================

def load_diaries(diaries_dir: str = "diaries") -> List[DiaryEntry]:
    entries: List[DiaryEntry] = []
    os.makedirs(diaries_dir, exist_ok=True)

    for path in glob.glob(os.path.join(diaries_dir, "*.txt")):
        filename = os.path.basename(path)
        name, _ = os.path.splitext(filename)

        # 期望格式: 2025-11-22.txt
        try:
            dt = datetime.strptime(name, "%Y-%m-%d")
        except ValueError:
            # 名字不是日期也无所谓，只是排序会靠前一点
            dt = datetime(1970, 1, 1)

        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()

        if text:
            entries.append(DiaryEntry(date=dt, text=text, path=path))

    # 按日期从旧到新
    entries.sort(key=lambda e: e.date)
    return entries


# ===================== 调用本地 Qwen =====================

def call_qwen(messages: List[dict]) -> str:
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "qwen2.5:7b",
        "messages": messages,
        "stream": False,
    }

    try:
        resp = requests.post(url, json=payload, timeout=600)
    except requests.RequestException as e:
        raise RuntimeError(f"调用 Ollama 失败: {e}")

    if resp.status_code != 200:
        raise RuntimeError(f"Ollama 返回错误状态码 {resp.status_code}: {resp.text}")

    data = resp.json()
    if "message" not in data or "content" not in data["message"]:
        raise RuntimeError(f"Ollama 返回格式异常: {data}")

    return data["message"]["content"]


# ===================== Prompt 构造 =====================

def build_style_system_prompt(
    diary_samples: List[DiaryEntry],
    target_lang: str = "zh",
    max_chars: int = 3000,
) -> str:
    """
    max_chars: 为了防止把太多日记一次性塞给模型，做个字符上限。
    """

    if not diary_samples:
        # 没有任何日记样本时，使用一个通用的人格提示，不再依赖示例文本
        base_prompt = """
        你是一个帮我写日记、陪我聊天的 AI 助手。

        要求：
        1. 语气自然、口语化，可以像和朋友聊天一样，不要官方公文腔，不要鸡汤模板。
        2. 我说今天发生了什么，你可以帮我整理成一小段日记；如果我只是随便聊天，就正常聊天，不要强行总结。
        3. 当我问学习、英语、技术之类的问题时，内容上要讲清楚、讲准确，表达上保持自然就行。
        4. 不要替我乱编具体经历和设定，如果我没提到，就少往我身上安人设。
        """.strip()

        if target_lang == "zh":
            return base_prompt + "\n\n优先使用中文回答，除非我明确要求用英文。"
        else:
            return base_prompt + "\n\nPrefer to answer in English unless I explicitly ask for Chinese."

    if target_lang == "zh":
        lang_instruction = "优先使用中文回答，除非我明确要求用英文。"
    else:
        lang_instruction = "优先使用英文回答，但语气尽量贴近日记示例。"

    # 把样本按从新到旧倒着拼，直到接近 max_chars
    pieces = []
    total = 0
    for e in reversed(diary_samples):
        block = f"【日期：{e.date.strftime('%Y-%m-%d')}】\n{e.text}\n"
        block_len = len(block)
        if total + block_len > max_chars:
            break
        pieces.append(block)
        total += block_len

    if not pieces:
        # 极端情况：单篇日记就已经超过 max_chars，那就只截一部分
        e = diary_samples[-1]
        truncated = (e.text[: max_chars - 50] + "...") if len(e.text) > max_chars else e.text
        pieces = [f"【日期：{e.date.strftime('%Y-%m-%d')}】\n{truncated}\n"]

    samples_block = "\n\n".join(pieces[::-1])  # 再翻回按时间正序

    system_prompt = f"""
    你是一个“风格适配器”，不是日记助手。

    你的职责只有两件事：
    1. 从下面这些日记中学习这个人的说话方式、吐槽习惯、节奏和用词偏好；
    2. 之后无论我让你做什么任务（造句、改写、翻译、写范文、做练习等），都用这种风格来表达。

    {lang_instruction}

    【日记示例开始】
    {samples_block}
    【日记示例结束】

    具体要求：

    1. 我提出什么任务，你就只做这个任务，不要额外加戏，不要主动提议“帮我写今天的日记”“要不要我总结一下今天”之类。
    2. 当我问技术问题、语法问题、学习规划时：内容上优先保证正确、清楚；在表达上尽量贴近日记里的说话方式。
    3. 当我说“帮我练某个语法点（例如虚拟语气、完成时态）”时：
       - 必须严格满足我要求的语法结构和数量（例如“写 5 句虚拟语气句子”）；
       - 在满足语法的前提下，主题、吐槽点、语气尽量像日记作者，比如围绕上班、英语、身体状况、纠结心态等。
    4. 除非我明确说“帮我写一篇/一段日记”，否则不要替我编今天发生了什么事情，不要给我安排人格设定和人生剧情。
    5. 回答可以比原始日记更有逻辑、更有条理，但不要变成官方口吻或鸡汤文，不要强行加“加油，你可以的”这一类模板安慰语。

    如果你需要补充细节，可以适度合理发挥，但不要与示例日记已经体现的人设、背景明显矛盾。
    """.strip()

    return system_prompt


# ===================== 对话封装 =====================

class DiaryPersonaBot:
    def __init__(
        self,
        diaries_dir: str = "diaries",
        num_samples: int = 5,
        target_lang: str = "zh",
    ):
        self.entries = load_diaries(diaries_dir)
        self.num_samples = num_samples
        self.target_lang = target_lang

    def _pick_recent_samples(self) -> List[DiaryEntry]:
        # 选最近 num_samples 篇
        return self.entries[-self.num_samples :]

    def chat(self, user_input: str) -> str:
        samples = self._pick_recent_samples()
        system_prompt = build_style_system_prompt(
            diary_samples=samples,
            target_lang=self.target_lang,
            max_chars=3000,  # 可以自行调小/调大
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        reply = call_qwen(messages)
        return reply


# ===================== 命令行测试入口 =====================

def main():
    bot = DiaryPersonaBot(
        diaries_dir="diaries",
        num_samples=5,     # 用最近 5 篇日记做风格样本
        target_lang="zh",  # 现在先中文，将来切英文就改成 "en"
    )

    print("日记人格 Qwen 已加载。（Ctrl+C 退出）")
    print("建议先试：比如输『帮我写一段今天的流水账日记，主要写工作和英语学习。』\n")

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出。")
            break

        if not user_input:
            continue

        try:
            reply = bot.chat(user_input)
        except NotImplementedError as e:
            print(f"[错误] 你还没实现 call_qwen(): {e}")
            break
        except Exception as e:
            print(f"[调用出错] {e}")
            continue

        print("\nAI:")
        print(reply)
        print()


if __name__ == "__main__":
    main()