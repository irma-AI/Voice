# Swedish phone numbers reserved for fiction

Question: which Swedish phone numbers are officially reserved so that synthetic data (the Faker-based seed and tests) can use them without ever reaching a real person?

## The reserved ranges

PTS (Post- och telestyrelsen, the Swedish numbering regulator) lists five reserved series on its page "Telefonnummer till böcker och filmer". The page says not to use real numbers in films or books because that can cause trouble for whoever has the number, and that PTS has reserved these series to use instead. ([PTS](https://pts.se/internet-och-telefoni/telefonnummer-och-adressering/telefonnummer-till-bocker-och-filmer/), page updated 2024-05-14, read 2026-10-21)

| Kind | National form (PTS's wording) | E.164 | Count |
|---|---|---|---|
| Mobile | 070-1740605 to 070-1740699 | +46701740605 to +46701740699 | 95 |
| Fixed, Göteborg | 031-3900600 to 031-3900699 | +46313900600 to +46313900699 | 100 |
| Fixed, Malmö | 040-6280400 to 040-6280499 | +46406280400 to +46406280499 | 100 |
| Fixed, Stockholm | 08-46500400 to 08-46500499 | +46846500400 to +46846500499 | 100 |
| Fixed, Kiruna | 0980-319200 to 0980-319299 | +46980319200 to +46980319299 | 100 |

PTS's own examples: 070-1740635, 031-3900642, 040-6280473, 08-46500456, 0980-319247.

The mobile series starts at 05, not 00: 070-1740600 to 070-1740604 are not in the list.

E.164 form: drop the leading national prefix 0 and add +46. The Swedish numbering plan says the prefix 0 is not part of the E.164 number, and gives PTS's own 08-678 55 00 as the example. ([PTS, Svenska telefoninummerplanen, sammanställning 2026-05-18](https://www.pts.se/contentassets/c67be6d4f65a456d9ed86a2542505b7b/nrplansammanstallning-2026-05-18.pdf), read 2026-10-21)

SVT reported the mobile series on 2020-09-07. It quotes the series as usable only by made-up people, and says there are fixed-line numbers for four cities, without naming them. That count matches PTS's list. ([SVT](https://www.svt.se/kultur/hundratals-telefonnummer-reserveras-for-film-tv-och-bocker), read 2026-10-21)

## Are they guaranteed never to be assigned?

Not in writing that I could find.

- The PTS page says "reserverat" (reserved). It does not say the numbers will never be assigned, and it does not say what happens when one is dialled (unconnected, an announcement, or something else).
- The 2026-05-18 numbering plan compilation does not mention the fiction series at all. A text search for fiction, film, drama and reservation wording found only the plan's general "reserved for future use" blocks.
- PTS's numbering guidance (2025-09-01) says PTS may decide on the use *or reservation* of number resources, so a reservation is a PTS decision. No decision number for these series is cited on the page. ([PTS, Vägledning nummer, 2025-09-01](https://pts.se/contentassets/f23691a018f44aa08fa2191dbeae62e0/vagledning---nummer---svensk-2025-09-01.pdf), read 2026-10-21)
- Not checked: PTS's "Sök operatör" lookup (https://nummer.pts.se/NbrSearch) would show which operator, if any, holds these blocks. It is a form POST, and I did not submit it.
- ITU-T E.164 sets the number format only. I found no ITU reservation of Swedish numbers for fiction, and none is expected: national number use is up to PTS.

In practice these are the only Swedish numbers a regulator has set aside for this purpose. The risk is that someone dials one, not that it belongs to a person. Synthetic data should still never be sent to a real carrier.

## Can Faker's sv_SE provider produce real numbers?

Yes. `faker==40.43.0`, `faker/providers/phone_number/sv_SE/__init__.py`, fills formats such as `08-### ## ##`, `0##-### ## ##` and `+46 (0)## ## ## ##` with random digits. Nothing restricts the output to the reserved series.

- A 20,000-number sample (seed 1) gave 1,233 numbers starting with 07 (mobile shape). None of them fell in 070-1740605..99.
- Outputs like `08-391 50 00` are plausible real Stockholm numbers.
- Some outputs are not valid Swedish numbers at all, for example `0063-60 83 77` (00 is the international prefix).

So Faker's `phone_number()` must not be used where a number could be dialled, texted or shown as real.

## Recommendation

Use only the PTS series. The smallest generator, in E.164:

```python
SAFE_SE_NUMBERS = (
    [f"+467017406{n:02d}" for n in range(5, 100)]  # mobile 070-1740605..99
    + [f"+463139006{n:02d}" for n in range(100)]   # Göteborg 031-3900600..99
    + [f"+464062804{n:02d}" for n in range(100)]   # Malmö 040-6280400..99
    + [f"+468465004{n:02d}" for n in range(100)]   # Stockholm 08-46500400..99
    + [f"+469803192{n:02d}" for n in range(100)]   # Kiruna 0980-319200..99
)
```

Simpler still for a seed: `faker.random_element(SAFE_SE_NUMBERS)`, or a mobile-only list `[f"+467017406{n:02d}" for n in range(5, 100)]` when one kind of number is enough. A test can assert every seeded number is in the list.
