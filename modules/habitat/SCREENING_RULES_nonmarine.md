# Screening rules: non-marine (freshwater / brackish inland) Polychaeta

Scope follows Glasby et al. (2009, Zootaxa 2070): polychaetes (incl. Aeolosomatidae, Histriobdellidae,
Parergodrilidae, Potamodrilidae, Hrabeiella) recorded from fresh water (rivers, lakes, springs, caves,
groundwater, hyporheic, phytotelmata), inland saline/brackish lakes and seas (e.g. Caspian, Aral),
oligohaline upper estuaries/coastal lagoons where they tolerate fresh water, or terrestrial/soil habitats.
Clitellata (oligochaetes, leeches) are OUT of scope.

Decide for each work (judge only from title, venue, abstract; never add facts):
- `yes`   — describes a new polychaete species/genus from such habitats; reports a polychaete species in fresh
            water, inland saline water, or oligohaline water (≈ <5 psu) with the species named or clearly
            implied; first record / invasion of a non-marine polychaete; taxonomic revision, checklist or review
            of non-marine polychaetes; physiology/ecology paper whose subject is a named non-marine polychaete
            species (it may document habitat range).
- `maybe` — a regional freshwater/estuarine benthos survey or a genus revision that may list non-marine
            polychaetes but the abstract does not name them; old reference without abstract whose title names
            a candidate genus (Namalycastis, Namanereis, Lycastoides, Stenoninereis, Manayunkia, Caobangia,
            Aeolosoma, Stratiodrilus, Hypania, Marenzelleria, Ficopomatus, Laonome, Dentinephtys, Tylorrhynchus,
            Hediste, Pisione etc.).
- `no`    — fully marine work; Clitellata only; non-annelid; methods/maths/ecology without polychaete taxa;
            pollution/biomarker study using a polychaete only as test organism without habitat information.

Output TSV (tab-separated, header line): `id	decision	reason`
Reason ≤ 20 words; quote the key phrase (e.g. "new species from a freshwater cave in Mexico").
