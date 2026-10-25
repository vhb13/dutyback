# DutyBack demo video: narration script

The video (`docs/DutyBack_demo.mp4`) has a synthetic voiceover (Kokoro, open source, voice af_heart).
If you'd rather use your own voice, open the video in iMovie, mute the original audio, use Record Voiceover and read these lines as each scene plays.

**Title card**
"This is DutyBack. It helps small importers get back tariffs that were struck down, before the deadlines pass."

**The problem**
"In February, the Supreme Court struck down the IEEPA tariffs. About a hundred and sixty six billion dollars was paid by more than three hundred thousand importers. But refunds are not automatic. Each customs entry has its own clock. Eighty days after it liquidates, CBP's online refund system stops accepting it. After a hundred and eighty days, even a protest is too late."

**What's not automated**
"Big companies have customs lawyers for this. A small business has a folder of paperwork, and a broker who is busy with everyone else. The sorting, entry by entry, is the part nobody has automated."

**Pick the Lotus sample**
"Here's Lotus Tile and Stone, a made-up tile importer. Its paperwork is thirteen customs entry summaries and a broker statement, and every broker formats these differently."

**Run (sped up)**
"I start a run. Code screens the files first. Then a Reader agent pulls out every entry, with the exact text it came from. Code checks every quote, date and dollar amount against the documents. A Checker agent with its own search tools looks for anything missed. This takes about a minute and a half. I've sped it up."

**Results**
"Here's the answer. About thirty nine thousand dollars can go into CAPE now, or after one quick fix. Twenty three thousand needs a protest. And one entry, worth sixty seven hundred dollars, has its last day today."

**Entries table**
"Every entry is sorted by deadline. The route and the dollar amount come from plain code that follows CBP's published rules. The agents never decide them."

**One entry's evidence**
"Click an entry and you see why. The quote from the broker statement, the duty line from the customs form, and every check the code ran."

**Section 301 entry**
"This granite entry paid Section 301 tariffs too. Those are not part of this refund, so only the two IEEPA lines are counted. Getting that wrong would overclaim by almost four thousand dollars."

**Action plan and broker email**
"The Advisor agent turns the results into a plan in plain English, soonest deadline first, and drafts an email to the broker. Code removes any sentence with a number or date that doesn't match the rules engine."

**Deadlines view**
"The deadlines view shows how much time each entry has left. Every week, some money slides from file online, to needs a protest, to waiting on the court."

**Downloads**
"And the owner leaves with files they can use: the list of entry numbers for CAPE, a calendar with a reminder before every deadline, and a printable summary for the broker."

**How this was made**
"This tab shows how the answer was made. Which agent ran, on which model, how long it took, and what it cost. This run cost about forty cents. The Checker made fifteen tool calls."

**Attack test**
"Now an attack. This statement hides a message in white text, and a visible note telling the AI to mark every entry as eligible. The screen removed both, and because routes come from code, the CAPE file did not change."

**Evaluation card**
"I tested it on four synthetic importers with hand checked answers, against one strong prompt with the same rules. On small clean files the prompt does well too. The difference is what happens when something goes wrong: DutyBack shows its evidence, and anything it can't verify goes to a person instead of into the filing."

**Impact card**
"For a typical small importer with fifty thousand dollars in these tariffs, acting today instead of waiting recovers about thirty five thousand. Waiting just one month pushes about four thousand more past a deadline."

**Close**
"DutyBack doesn't replace a customs broker. It makes sure a small business knows what it's owed, and acts before the deadline. Thanks for watching."
