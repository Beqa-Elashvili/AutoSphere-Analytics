"""Bilingual (Georgian / English) customer feedback templates.

Each (topic, sentiment) pair has several phrasings. Labelling convention, also
used to evaluate the AI classifier in Phase 8:
  * topic     = the main subject of the feedback (the issue, if there is one)
  * sentiment = overall tone; mixed feedback containing a complaint is 'negative'
                (e.g. "service was good, but the wait was very long" ->
                 negative / waiting_time)
"""

TOPICS = [
    "service_quality", "waiting_time", "price", "staff",
    "product_quality", "availability", "complaint", "other",
]
SENTIMENTS = ["positive", "neutral", "negative"]

TEMPLATES: dict[tuple[str, str], dict[str, list[str]]] = {
    # ------------------------------------------------------------------ service quality
    ("service_quality", "positive"): {
        "en": [
            "Excellent service, the car runs perfectly now.",
            "Very professional work, everything was fixed properly.",
            "The maintenance was done carefully. Highly recommend.",
            "Great job by the service team, my car feels like new.",
        ],
        "ka": [
            "შესანიშნავი სერვისი, მანქანა იდეალურად მუშაობს.",
            "ძალიან პროფესიონალურად გააკეთეს ყველაფერი.",
            "სერვისით ძალიან კმაყოფილი ვარ, ყველაფერი ხარისხიანად გაკეთდა.",
            "მადლობა სერვისის გუნდს, მანქანა ახალივით არის.",
        ],
    },
    ("service_quality", "neutral"): {
        "en": [
            "Service was okay, nothing special.",
            "Average service experience.",
            "The repair was done, let's see how long it lasts.",
        ],
        "ka": [
            "სერვისი ნორმალური იყო, განსაკუთრებული არაფერი.",
            "საშუალო მომსახურებაა.",
            "რემონტი გაკეთდა, ვნახოთ რამდენ ხანს გაძლებს.",
        ],
    },
    ("service_quality", "negative"): {
        "en": [
            "The problem was not fixed, I had to come back again.",
            "Poor quality repair, the noise is still there.",
            "After the service the check engine light came back on.",
            "Very disappointed with the quality of the work.",
        ],
        "ka": [
            "პრობლემა ვერ მოაგვარეს, ისევ მომიწია მისვლა.",
            "რემონტი უხარისხოდ გაკეთდა, ხმაური ისევ ისმის.",
            "სერვისის შემდეგ ძრავის შუქი ისევ აინთო.",
            "სამუშაოს ხარისხით ძალიან უკმაყოფილო ვარ.",
        ],
    },
    # ------------------------------------------------------------------ waiting time
    ("waiting_time", "positive"): {
        "en": [
            "Very fast service, I was done in less than an hour.",
            "No waiting at all, everything was on time.",
            "They finished earlier than promised.",
        ],
        "ka": [
            "ძალიან სწრაფად მომემსახურნენ, ერთ საათში დამთავრდა.",
            "ლოდინი საერთოდ არ მომიწია, ყველაფერი დროულად გაკეთდა.",
            "დაპირებულზე ადრე დაასრულეს.",
        ],
    },
    ("waiting_time", "neutral"): {
        "en": [
            "Waiting time was acceptable.",
            "It took a bit longer than expected, but it was fine.",
        ],
        "ka": [
            "ლოდინის დრო მისაღები იყო.",
            "ცოტა მეტი დრო დასჭირდა, ვიდრე ველოდი, მაგრამ ნორმალურია.",
        ],
    },
    ("waiting_time", "negative"): {
        "en": [
            "I waited for hours, way too long.",
            "The service was good, but the waiting time was very long.",
            "My car was supposed to be ready yesterday, still waiting.",
            "Too slow. Three days for a simple repair.",
        ],
        "ka": [
            "საათობით მომიწია ლოდინი, ძალიან დიდხანს.",
            "სერვისი კარგი იყო, მაგრამ ძალიან დიდხანს მომიწია ლოდინი.",
            "მანქანა გუშინ უნდა ყოფილიყო მზად, ისევ ველოდები.",
            "ძალიან ნელა მუშაობენ, მარტივ რემონტს სამი დღე მოანდომეს.",
        ],
    },
    # ------------------------------------------------------------------ price
    ("price", "positive"): {
        "en": [
            "Fair prices compared to other places.",
            "Good value for money.",
            "The discount was a nice surprise.",
        ],
        "ka": [
            "სხვა ადგილებთან შედარებით სამართლიანი ფასებია.",
            "ფასი ხარისხს შეესაბამება.",
            "ფასდაკლება სასიამოვნო სიურპრიზი იყო.",
        ],
    },
    ("price", "neutral"): {
        "en": ["Prices are average for the market.", "The price was as quoted."],
        "ka": ["ფასები ბაზრის საშუალოა.", "ფასი ისეთი იყო, როგორიც წინასწარ მითხრეს."],
    },
    ("price", "negative"): {
        "en": [
            "Too expensive, prices went up again.",
            "The final bill was much higher than the estimate.",
            "Overpriced parts, I can find them cheaper elsewhere.",
        ],
        "ka": [
            "ძალიან ძვირია, ფასები ისევ გაიზარდა.",
            "საბოლოო თანხა წინასწარ შეფასებულზე გაცილებით მეტი იყო.",
            "ნაწილები ზედმეტად ძვირია, სხვაგან უფრო იაფად ვიპოვი.",
        ],
    },
    # ------------------------------------------------------------------ staff
    ("staff", "positive"): {
        "en": [
            "The staff was very friendly and helpful.",
            "The consultant explained everything clearly.",
            "Polite and knowledgeable team.",
        ],
        "ka": [
            "პერსონალი ძალიან თავაზიანი და დამხმარე იყო.",
            "კონსულტანტმა ყველაფერი გასაგებად ამიხსნა.",
            "თავაზიანი და კომპეტენტური გუნდია.",
        ],
    },
    ("staff", "neutral"): {
        "en": ["Staff was okay.", "The advisor answered my questions."],
        "ka": ["პერსონალი ნორმალური იყო.", "კონსულტანტმა კითხვებზე მიპასუხა."],
    },
    ("staff", "negative"): {
        "en": [
            "The staff was rude and not interested in helping.",
            "Nobody answered my calls.",
            "The advisor did not explain what was replaced.",
        ],
        "ka": [
            "პერსონალი უხეში იყო და დახმარების სურვილი არ ჰქონდათ.",
            "ზარებს არავინ პასუხობდა.",
            "კონსულტანტმა არ ამიხსნა, რა შეცვალეს.",
        ],
    },
    # ------------------------------------------------------------------ product quality
    ("product_quality", "positive"): {
        "en": [
            "The tires are excellent, very quiet on the road.",
            "Great quality battery, works perfectly in winter.",
            "The accessories are high quality.",
        ],
        "ka": [
            "საბურავები შესანიშნავია, გზაზე ძალიან ჩუმია.",
            "ხარისხიანი აკუმულატორია, ზამთარშიც იდეალურად მუშაობს.",
            "აქსესუარები მაღალი ხარისხისაა.",
        ],
    },
    ("product_quality", "neutral"): {
        "en": ["The product is fine, as described.", "Average quality for the price."],
        "ka": ["პროდუქტი ნორმალურია, როგორც აღწერილი იყო.", "ფასთან შედარებით საშუალო ხარისხია."],
    },
    ("product_quality", "negative"): {
        "en": [
            "The part broke after two weeks.",
            "Poor quality product, I want a replacement.",
            "The battery died after one month.",
        ],
        "ka": [
            "ნაწილი ორ კვირაში გაფუჭდა.",
            "უხარისხო პროდუქტია, გამოცვლა მინდა.",
            "აკუმულატორი ერთ თვეში დაჯდა.",
        ],
    },
    # ------------------------------------------------------------------ availability
    ("availability", "positive"): {
        "en": ["Everything I needed was in stock.", "They had the exact part for my car."],
        "ka": [
            "ყველაფერი, რაც მჭირდებოდა, მარაგში ჰქონდათ.",
            "ზუსტად ის ნაწილი ჰქონდათ, რაც ჩემს მანქანას სჭირდებოდა.",
        ],
    },
    ("availability", "neutral"): {
        "en": ["The part had to be ordered, it took a few days."],
        "ka": ["ნაწილი შეკვეთით მოიტანეს, რამდენიმე დღე დასჭირდა."],
    },
    ("availability", "negative"): {
        "en": [
            "The part was out of stock again.",
            "They did not have the tires I needed, I had to go elsewhere.",
            "Waiting two weeks for a part that should be in stock.",
        ],
        "ka": [
            "ნაწილი ისევ არ ჰქონდათ მარაგში.",
            "საჭირო საბურავები არ ჰქონდათ, სხვაგან მომიწია წასვლა.",
            "ორი კვირაა ველოდები ნაწილს, რომელიც მარაგში უნდა ყოფილიყო.",
        ],
    },
    # ------------------------------------------------------------------ formal complaint
    ("complaint", "negative"): {
        "en": [
            "I want to file an official complaint.",
            "This is unacceptable, I demand a refund.",
            "Worst experience ever, I will never come back.",
            "My car was damaged during the service.",
        ],
        "ka": [
            "ოფიციალური საჩივრის დაწერა მინდა.",
            "ეს მიუღებელია, თანხის დაბრუნებას ვითხოვ.",
            "ყველაზე ცუდი გამოცდილება, აღარასდროს მოვალ.",
            "სერვისის დროს მანქანა დამიზიანეს.",
        ],
    },
    # ------------------------------------------------------------------ other
    ("other", "neutral"): {
        "en": [
            "Is it possible to book online next time?",
            "Please send me the invoice by email.",
            "Do you work on Sundays?",
        ],
        "ka": [
            "შემდეგ ჯერზე ონლაინ ჯავშანი შეიძლება?",
            "ინვოისი ელფოსტაზე გამომიგზავნეთ, გთხოვთ.",
            "კვირას მუშაობთ?",
        ],
    },
    ("other", "positive"): {
        "en": ["Thank you!", "Everything was fine, thanks."],
        "ka": ["გმადლობთ!", "ყველაფერი კარგად იყო, მადლობა."],
    },
}

# Topic mix depends on what the feedback is about.
SERVICE_TOPIC_WEIGHTS = {
    "service_quality": 0.30, "staff": 0.18, "price": 0.14, "waiting_time": 0.14,
    "complaint": 0.07, "other": 0.07, "availability": 0.04, "product_quality": 0.06,
}
SALES_TOPIC_WEIGHTS = {
    "product_quality": 0.30, "price": 0.24, "staff": 0.20, "availability": 0.10,
    "service_quality": 0.05, "waiting_time": 0.03, "complaint": 0.04, "other": 0.04,
}
# Baseline sentiment probabilities (positive, neutral, negative).
BASE_SENTIMENT = (0.55, 0.20, 0.25)
