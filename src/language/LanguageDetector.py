from lingua import Language, LanguageDetectorBuilder

languages = [Language.ENGLISH]
detector = LanguageDetectorBuilder.from_languages(*languages).build()

# pip install lingua-language-detector

def detect_language(text):
    """Detect the language of a single text string."""
    if not text:
        return None
    return detector.detect_language_of(text)

# if __name__ == "__main__":
#     text_samples = [
#         "Hello, how are you?",
#     ]

#     for text in text_samples:
#         lang = detect_language(text)
#         print(f"{text[:30]!r} → {lang}")