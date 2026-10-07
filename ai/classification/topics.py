"""Bilingual topic keywords for the local classifier (stems for Georgian).

PRIORITY resolves ties: specific, actionable topics beat generic ones.
"""

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "complaint": [
        "complaint", "refund", "unacceptable", "never come back", "worst", "damaged",
        "საჩივ", "თანხის დაბრუნ", "მიუღებელ", "აღარასდროს", "ყველაზე ცუდი", "დამიზიანეს",
    ],
    "availability": [
        "stock", "had the exact part", "did not have", "go elsewhere", "had to be ordered",
        "everything i needed", "მარაგ", "ჰქონდათ", "შეკვეთით", "სხვაგან მომიწია წასვლა",
    ],
    "waiting_time": [
        "wait", "slow", "fast", "quick", "on time", "hours", "days", "earlier than",
        "ready yesterday", "less than an hour", "took longer", "took a bit longer",
        "ლოდინ", "ველოდ", "დიდხანს", "ნელა", "სწრაფად", "დროულად", "საათ", "დღე", "მოანდომეს",
        "ადრე დაასრულეს", "მეტი დრო", "მზად",
    ],
    "price": [
        "price", "expensive", "cheap", "overpriced", "value for money", "bill", "estimate", "discount",
        "quoted", "ფას", "ძვირ", "იაფ", "თანხა", "ფასდაკლებ", "შეფასებ",
    ],
    "staff": [
        "staff", "consultant", "advisor", "rude", "polite", "friendly", "helpful", "calls",
        "explain", "knowledgeable",
        "პერსონალ", "კონსულტანტ", "თავაზიან", "უხეშ", "ზარებს", "ამიხსნა", "კომპეტენტურ",
    ],
    "product_quality": [
        "tire", "tyre", "battery", "part broke", "product", "accessor", "replacement", "died", "quality for the price", "average quality",
        "საბურავ", "აკუმულატორ", "გაფუჭდა", "პროდუქტ", "აქსესუარ", "გამოცვლა", "ხარისხისაა", "ხარისხია ", "საშუალო ხარისხ",
    ],
    "service_quality": [
        "service", "repair", "fixed", "maintenance", "the work", "check engine", "noise", "problem",
        "სერვის", "რემონტ", "მოაგვარეს", "გააკეთეს", "სამუშაო", "მომსახურება", "ძრავის", "ხმაური", "პრობლემა",
    ],
    "other": [
        "book online", "invoice", "sunday", "thank you", "thanks",
        "ჯავშან", "ინვოის", "კვირას", "გმადლობთ", "მადლობა",
    ],
}

PRIORITY = ["complaint", "availability", "waiting_time", "price", "staff", "product_quality",
            "service_quality", "other"]
