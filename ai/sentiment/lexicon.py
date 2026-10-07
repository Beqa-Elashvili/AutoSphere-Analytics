"""Bilingual sentiment lexicon for the local (rule-based) classifier.

Georgian is agglutinative, so most entries are STEMS matched as substrings
('ძვირ' matches ძვირი, ძვირია, ზედმეტად ძვირ...). English entries are lowercase
words or phrases. Phrases are checked before single words so that
"no waiting" is not read as a negative "waiting".
"""

# Phrases that would be mis-read word by word (checked first, then removed from the text).
POSITIVE_PHRASES = [
    "no waiting", "on time", "earlier than promised", "less than an hour", "in stock",
    "value for money", "had the exact", "everything i needed", "like new", "highly recommend",
    "ლოდინი საერთოდ არ", "საერთოდ არ მომიწია", "დროულად", "ადრე დაასრულეს", "ერთ საათში",
    "მარაგში ჰქონდათ", "ზუსტად ის ნაწილი ჰქონდათ", "ახალივით", "შეესაბამება",
]
NEGATIVE_PHRASES = [
    "not fixed", "out of stock", "did not have", "did not explain", "nobody answered", "came back on",
    "too slow", "way too long", "waited for hours", "still waiting", "higher than the estimate",
    "much higher", "never come back", "worst experience", "should be in stock", "two weeks",
    "ვერ მოაგვარეს", "არ ჰქონდათ", "არ ამიხსნა", "არავინ პასუხობდა", "ისევ აინთო", "ისევ ისმის",
    "ისევ მომიწია", "ისევ ველოდები", "ისევ გაიზარდა", "გაცილებით მეტი", "სხვაგან მომიწია",
    "საათობით", "დიდხანს", "ზედმეტად", "ორი კვირაა", "აღარასდროს",
]
NEUTRAL_PHRASES = [
    "nothing special", "as described", "as quoted", "answered my questions", "let's see",
    "had to be ordered", "was fine", "it was fine", "average", "acceptable", "okay", "ok",
    "ნორმალურ", "საშუალო", "მისაღები", "ვნახოთ", "როგორც აღწერილი", "როგორიც წინასწარ",
    "მიპასუხა", "შეკვეთით",
]

POSITIVE_WORDS = [
    "excellent", "great", "good", "perfect", "perfectly", "professional", "recommend", "fast",
    "fair", "friendly", "helpful", "polite", "clearly", "knowledgeable", "satisfied", "thank",
    "thanks", "quiet", "high quality", "nice", "surprise", "properly", "carefully",
    "შესანიშნავ", "კარგ", "იდეალურ", "პროფესიონალ", "კმაყოფილ", "მადლობ", "გმადლობთ",
    "სწრაფად", "სამართლიან", "სასიამოვნო", "თავაზიან", "დამხმარე", "გასაგებად", "კომპეტენტურ",
    "ჩუმი", "ხარისხიან", "მაღალი ხარისხის",
]
NEGATIVE_WORDS = [
    "poor", "disappointed", "rude", "expensive", "overpriced", "broke", "died", "slow",
    "unacceptable", "refund", "damaged", "complaint", "worst", "problem", "noise", "never",
    "replacement", "waited", "long",
    "უხარისხო", "უკმაყოფილო", "უხეში", "ძვირ", "გაფუჭდა", "დაჯდა", "ნელა", "საჩივ",
    "მიუღებელ", "ცუდი", "დამიზიანეს", "პრობლემა", "გამოცვლა", "ვითხოვ",
]

CONTRAST_MARKERS = [" but ", " however ", ", but", " მაგრამ ", ", მაგრამ"]
