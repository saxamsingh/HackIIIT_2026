"""Hindi, Hinglish and English vocabulary for triage. Tokens are lowercase; Devanagari is matched as-is."""

from __future__ import annotations

# canonical crop name by the word a farmer might use
CROPS: dict[str, str] = {
    "wheat": "wheat", "gehu": "wheat", "gehun": "wheat", "गेहूं": "wheat", "गेहूँ": "wheat", "गेहू": "wheat",
    "rice": "rice", "paddy": "rice", "dhan": "rice", "chawal": "rice", "धान": "rice", "चावल": "rice",
    "mustard": "mustard", "sarson": "mustard", "सरसों": "mustard",
    "maize": "maize", "makka": "maize", "makki": "maize", "मक्का": "maize",
    "sugarcane": "sugarcane", "ganna": "sugarcane", "गन्ना": "sugarcane",
    "potato": "potato", "aloo": "potato", "alu": "potato", "आलू": "potato",
    "bajra": "bajra", "बाजरा": "bajra",
    "soybean": "soybean", "soyabean": "soybean", "सोयाबीन": "soybean",
    "chana": "chickpea", "chickpea": "chickpea", "चना": "chickpea",
    "cotton": "cotton", "kapas": "cotton", "कपास": "cotton",
}

# Words that mark a question as being about spraying or dosing. Handled by a human, never by an agent.
PESTICIDES: frozenset[str] = frozenset({
    "chlorpyrifos", "imidacloprid", "cypermethrin", "glyphosate", "mancozeb", "carbendazim",
    "monocrotophos", "profenofos", "thiamethoxam", "atrazine", "paraquat",
    "endosulfan", "acephate", "dimethoate", "fipronil",
})
ADVISORY_WORDS: frozenset[str] = frozenset({
    "pesticide", "insecticide", "fungicide", "herbicide", "weedicide", "spray", "dawai", "dawa",
    "keetnashak", "keetnashi", "dose", "dosage", "pump", "khad", "khaad", "urea", "dap", "fertiliser",
    "fertilizer", "कीटनाशक", "दवा", "दवाई", "छिड़काव", "डोज़", "डोज", "खाद", "यूरिया",
})
# Units that only make sense for chemicals. kg, gram and litre are left out so "kitna kg bechun?" is a sell question.
DOSE_UNIT_WORDS: frozenset[str] = frozenset({"ml", "mg", "cc", "मिली", "मिलीलीटर"})
DOSE_QUESTION_WORDS: frozenset[str] = frozenset({"kitna", "kitni", "kitne", "कितना", "कितनी", "कितने"})

CLAIM_WORDS: frozenset[str] = frozenset({
    "claim", "insurance", "bima", "bheema", "pmfby", "hail", "hailstorm", "olavrishti", "ola", "nuksan",
    "nuksaan", "flood", "baadh", "बीमा", "ओला", "ओलावृष्टि", "नुकसान", "क्लेम", "बाढ़",
})
CLAIM_PHRASES: tuple[str, ...] = ("fasal kharab", "crop damage", "फसल खराब")

SUBSIDY_WORDS: frozenset[str] = frozenset({
    "subsidy", "scheme", "schemes", "yojana", "yojna", "anudan", "sahayata", "kcc",
    "सब्सिडी", "योजना", "अनुदान", "सहायता",
})
SUBSIDY_PHRASES: tuple[str, ...] = ("pm-kisan", "pm kisan", "pmkisan", "पीएम किसान")

SELL_WORDS: frozenset[str] = frozenset({
    "sell", "bechun", "bechna", "bechu", "bech", "bhav", "bhaav", "rate", "price", "mandi",
    "बेचूं", "बेचना", "भाव", "मंडी", "बेचें",
})
WHERE_WORDS: frozenset[str] = frozenset({"kahan", "kaha", "where", "कहां", "कहाँ"})

# Latin-script words that show a message is Hindi written in English letters.
HINGLISH_WORDS: frozenset[str] = frozenset({
    "kahan", "kaha", "bechun", "bechna", "bech", "kitna", "kitni", "kitne", "dalu", "daalu", "yojana",
    "anudan", "bima", "fasal", "kharab", "bhav", "bhaav", "gehu", "gehun", "dhan", "sarson", "hai", "kya",
    "kaise", "karun", "chahiye", "paas", "nuksan", "ola", "dawai", "sahayata", "mera", "meri", "mujhe",
    "batao", "bataiye", "kab", "wala", "ka", "ki", "ke", "ko",
})
