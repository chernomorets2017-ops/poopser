import os
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

STYLE_PROMPTS = {
    "hype": (
        "Ты крутой SMM-щик. Перепиши этот пост в хайповом стиле: "
        "короткие предложения, много эмодзи, КАПС на ключевых словах, "
        "интрига с первых слов. Без воды. Сохрани смысл."
    ),
    "short": (
        "Сожми этот пост до 2-3 предложений. Только суть, без лишнего. Никакой воды."
    ),
    "meme": (
        "Перепиши в мемном стиле: с юмором, сленгом, отсылками к "
        "интернет-культуре. Смешно, но по делу."
    ),
    "news": (
        "Перепиши как профессиональная новостная заметка: факты, "
        "нейтральный тон, структура. Заголовок + суть."
    ),
}


async def rewrite_post(text: str, style: str = "hype", custom_prompt: str = "") -> str:
    if not text.strip():
        return text
    system_prompt = (
        custom_prompt.strip()
        if custom_prompt.strip()
        else STYLE_PROMPTS.get(style, STYLE_PROMPTS["hype"])
    )
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Пост:\n\n{text[:2000]}"},
            ],
            max_tokens=600,
            temperature=0.85,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Ошибка нейронки: {e}")
        return text