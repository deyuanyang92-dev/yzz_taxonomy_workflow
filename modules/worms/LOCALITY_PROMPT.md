# Locality normalisation task (fixed sub-agent prompt)

Do NOT call the Agent tool. Use only Read / Write / Bash on files. No web access.

Input: `/mnt/n/yzz-分类工作流/cache/locality_inbox/todo_N.json` — a JSON list of strings. Each string is the original type-locality text of an animal species, possibly followed by ` || ` and extra higher-geography text supplied by WoRMS.
Output: `done_N.json` in the same folder — one JSON object. **Keys = the input strings exactly as given (including any ` || ` suffix, character for character).** Each value:

```json
{"Region": "", "Country": "", "ISO": "", "State/Province": "", "County/City": "", "Locality": "", "Water body": "", "Confidence": ""}
```

All values in **English** (ISO = two-letter country code):
- **Region**: ocean / sea basin / continent, e.g. North Atlantic Ocean, Western Pacific, Southern Ocean, Mediterranean Sea, Indian Ocean, Antarctica; for land points the continent.
- **Country**: present-day country (e.g. "Xiamen, China" -> China). Historical names mapped to today's country. Leave blank if unsure.
- **State/Province**: first-level administrative unit (Fujian, California, Provence-Alpes-Côte d'Azur).
- **County/City**: city, county, island group or other second-level unit (Xiamen).
- **Locality**: the finest place named in the original text, in modern English spelling (bay, harbour, island, reef, station area), e.g. "Agay". Keep the original wording for vague phrases ("off southern Chile").
- **Water body**: gulf / bay / sea / strait named in or implied by the text, e.g. Gulf of St Vincent, Mediterranean Sea, Taiwan Strait.
- **Confidence**: `High` (explicit, unambiguous) / `Medium` (light inference, e.g. only a city is given and the state comes from common knowledge) / `Low` (ambiguous homonym, archaic spelling, or you are unsure).

Hard rules:
1. **Judge only from the text.** If a field is not in the text and you cannot be certain, leave it as an empty string. Better blank than wrong.
2. Ambiguous names (Greenland, Santa Cruz, Port Elizabeth...): use the ` || ` suffix and context; if still uncertain leave the affected fields blank and set Confidence `Low`.
3. Pure open-water points (e.g. "Pacific Ocean, off southern Chile"): Country may be the nearest coastal state (Chile); State/Province and County/City stay blank; Confidence at most `Medium`.
4. Depth, station numbers, collection dates are not places — ignore them.
5. After roughly every 50 entries write the current results to `done_N.json` (overwrite) so an interruption loses nothing.
6. Final report is ONE line only: `done_N.json: X/Y done, Z low-confidence`. Do not paste results.
