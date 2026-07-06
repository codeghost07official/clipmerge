import logging
import random
import re


LOGGER = logging.getLogger(__name__)

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "for",
    "from", "have", "i", "in", "into", "is", "it", "make", "me", "my", "of",
    "on", "or", "our", "please", "show", "that", "the", "their", "them",
    "then", "there", "this", "to", "video", "want", "we", "with", "would",
    "you", "your", "create", "generate", "clip", "clips", "footage"
}

CONCEPT_EXPANSIONS = {
    "business": ["office meeting", "business team", "corporate workspace", "startup office"],
    "office": ["office meeting", "desk work", "business people", "modern workspace"],
    "technology": ["technology background", "computer coding", "data center", "digital interface"],
    "tech": ["technology background", "software developer", "digital network", "computer screen"],
    "nature": ["nature landscape", "forest drone", "mountain landscape", "wild scenery"],
    "forest": ["forest trail", "trees sunlight", "woodland landscape", "green nature"],
    "ocean": ["ocean waves", "sea coastline", "beach drone", "water surface"],
    "beach": ["beach waves", "coastal sunset", "sand shore", "tropical beach"],
    "city": ["city skyline", "urban street", "traffic timelapse", "downtown buildings"],
    "urban": ["urban street", "city skyline", "downtown traffic", "modern buildings"],
    "travel": ["travel destination", "airport travel", "road trip", "tourist landmark"],
    "food": ["cooking close up", "restaurant kitchen", "fresh ingredients", "food preparation"],
    "fitness": ["gym workout", "running outdoors", "fitness training", "healthy lifestyle"],
    "health": ["healthy lifestyle", "doctor consultation", "wellness routine", "medical care"],
    "music": ["music performance", "concert crowd", "recording studio", "musician close up"],
    "education": ["students learning", "classroom study", "online education", "teacher lesson"],
    "finance": ["financial charts", "business analysis", "stock market", "money planning"],
    "car": ["car driving", "road traffic", "vehicle close up", "highway drive"],
    "sports": ["sports training", "athlete running", "team practice", "stadium action"],
    "family": ["happy family", "parents children", "home lifestyle", "family outdoors"],
    "home": ["cozy home", "interior lifestyle", "living room", "house exterior"],
    "space": ["night sky", "stars timelapse", "abstract universe", "space background"],
    "medical": ["doctor consultation", "hospital care", "medical equipment", "healthcare worker"],
    "fashion": ["fashion model", "clothing details", "runway show", "style portrait"],
    "energy": ["solar panels", "wind turbines", "power plant", "renewable energy"],
    "water": ["water surface", "river flow", "ocean waves", "rain drops"],
    "summer": ["summer beach", "sunny outdoors", "vacation lifestyle", "golden sunlight"],
    "winter": ["snow landscape", "winter forest", "cold weather", "snow falling"],
}

VISUAL_MODIFIERS = [
    "cinematic", "b roll", "wide shot", "close up", "slow motion",
    "aerial", "establishing shot", "timelapse", "background"
]

RELEVANCE_STOP_WORDS = {
    "about", "after", "all", "also", "and", "are", "around", "as", "at", "beautiful",
    "being", "between", "bright", "can", "cinematic", "create", "creating", "during",
    "each", "exploring", "for", "from", "great", "horizon", "into", "its",
    "light", "like", "look", "looking", "nice", "of", "on", "over", "shots", "some",
    "the", "their", "through", "to", "while", "with", "without"
}


def normalize_prompt(prompt):
    return re.sub(r"\s+", " ", prompt.strip().lower())


def tokenize(prompt):
    return re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{1,}", normalize_prompt(prompt))


def important_terms(prompt):
    words = [word.strip("-'") for word in tokenize(prompt)]
    words = [word for word in words if word and word not in STOP_WORDS and word not in RELEVANCE_STOP_WORDS and len(word) > 2]
    return [word for word in dict.fromkeys(words)]


def prompt_terms(prompt):
    terms = [word for word in tokenize(prompt) if word and word not in STOP_WORDS and word not in RELEVANCE_STOP_WORDS and len(word) > 2]
    return [word for word in dict.fromkeys(terms)]


def build_search_queries(prompt, max_keywords=12):
    rng = random.SystemRandom()
    normalized = normalize_prompt(prompt)
    terms = important_terms(prompt)
    concept_terms = [term for term in terms if term not in RELEVANCE_STOP_WORDS]

    if not concept_terms:
        concept_terms = [term for term in terms if len(term) > 2]

    queries = []

    if 3 <= len(normalized) <= 120:
        queries.append(normalized)

    for term in concept_terms[:6]:
        queries.append(term)

    semantic_expansions = {
        "astronaut": ["astronaut spacewalk", "astronaut moon landing", "astronaut exploration", "spacewalk astronaut"],
        "moon": ["moon surface", "lunar surface", "moon landscape", "earth from moon"],
        "earth": ["earth from space", "earth horizon", "earth rise"],
        "space": ["space exploration", "space mission", "cosmic landscape", "outer space"],
    }

    if concept_terms:
        primary = concept_terms[:4]
        for term in primary:
            queries.append(f"{term} space")
            queries.append(f"{term} footage")
            queries.append(f"{term} scene")
            if term in semantic_expansions:
                queries.extend(semantic_expansions[term])

    if len(primary := concept_terms[:4]) >= 2:
        for first, second in zip(primary, primary[1:]):
            queries.append(f"{first} {second}")
            queries.append(f"{first} {second} footage")

    for term in concept_terms[:4]:
        if rng.random() > 0.3:
            queries.append(f"{rng.choice(VISUAL_MODIFIERS)} {term}")

    fallback_contexts = ["space", "moon", "astronaut", "earth", "planet", "cosmos"]
    for context in rng.sample(fallback_contexts, k=min(3, len(fallback_contexts))):
        if context not in concept_terms:
            queries.append(context)

    unique_queries = []
    seen = set()
    for query in queries:
        cleaned = re.sub(r"[^a-zA-Z0-9\s'-]", " ", query)
        cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
        if len(cleaned) < 3 or cleaned in seen:
            continue
        seen.add(cleaned)
        unique_queries.append(cleaned)
        if len(unique_queries) >= max_keywords:
            break

    return unique_queries


def phrases_from_terms(terms):
    phrases = []
    for size in (3, 2):
        for index in range(0, max(0, len(terms) - size + 1)):
            phrase = " ".join(terms[index:index + size])
            if phrase not in phrases:
                phrases.append(phrase)
    return phrases


def generate_keywords(prompt, max_keywords=12):
    """Create varied stock-footage search phrases without any external AI API."""
    terms = important_terms(prompt)
    if not terms:
        raise ValueError("Enter a more descriptive prompt.")

    queries = build_search_queries(prompt, max_keywords=max_keywords)
    if len(queries) < 3:
        queries.extend(terms[:max_keywords])

    LOGGER.debug("Generated search queries: %s", queries)
    return queries
