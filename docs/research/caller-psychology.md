# What callers prefer in an AI voice agent

Read 2026-10-19. Petter's question: callers seem to prefer a woman's voice, but which other things make a Caller trust the agent, feel well served and finish the errand, and how do we steer them? This note covers voice, conversation behaviour, the AI disclosure, Swedish norms, and what we control: the voice name, the system instruction, the VAD settings and the eval Scenarios. It builds on `docs/research/gemini-live-voice-and-language.md`, which covers the Gemini settings in depth.

## Scope: what this excludes, and why

This note covers persuasion that serves the Caller only: warmth, competence, clarity, pacing, turn-taking, empathy, less effort and calm handling of frustration. It leaves out, on purpose, every technique that works against the Caller:

- hiding, delaying or blurring that the agent is an AI, including "disclose late" tactics;
- false urgency or scarcity;
- exploiting biases against the Caller's interest;
- pressure selling and dark patterns, such as making it hard to end the call.

The reasons are law and product:

- [EU AI Act, Regulation (EU) 2024/1689, Art. 50](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) ([readable article page](https://artificialintelligenceact.eu/article/50/), read 2026-10-19). An AI system that talks to people must tell them so, "clear and distinguishable", "at the latest at the first interaction" (Art. 50(1) and 50(5)). It applies from 2 August 2026. The 2026 Digital Omnibus did not move Art. 50(1), according to law-firm notes; not checked against the Official Journal. Our disclosure is legally required and Petter-approved, so it stays first and word for word.
- [Unfair Commercial Practices Directive 2005/29/EC](https://eur-lex.europa.eu/eli/dir/2005/29/oj) (read 2026-10-19):
  - Art. 6 and 7 forbid misleading actions and omissions, including about who the trader is.
  - Art. 8 and 9 forbid aggressive practices: harassment, coercion and undue influence.
  - Annex I point 7 bans, in all circumstances, falsely saying an offer lasts only a very limited time to force a decision.

  An agent that answers for a Business is part of its commercial practice.

A legal reading of either text goes to Petter, and for Jobylon matters to the CEO. Nothing here is legal advice.

## How to read the sources

Each source has a link, was read on 2026-10-19, and carries one of four strength marks:

| Mark | Meaning |
|---|---|
| **read** | the full text or the official page was read |
| **abstract** | only the abstract or the publisher's page |
| **not checked** | only a search summary or press coverage; the claim may be off |
| **contested** | other studies disagree |

Most academic sources are **abstract** or **not checked**. Google's pages were read through a summarising fetch, as in the earlier note. Papers are cited by title, venue and year. Where a paper's own address carries its authors' names, the link is a Google Scholar search for its title instead. Nothing was heard or measured here: no call was made and no Gemini credit was spent.

## 1. Voice gender: does everyone prefer a woman's voice?

**Verdict: no.** People often *say* they prefer a female synthetic voice and call it "warmer". Controlled studies find small, mixed or no effects of voice gender on trust, competence or task success. Where gender matters, it interacts with the topic and with the listener. A native, clear, warm-sounding Swedish voice matters more than its gender. Choose the voice by blind listening for warmth and clarity in Swedish, not by gender.

| Finding | Source | Strength |
|---|---|---|
| People applied gender stereotypes to computer voices: a male voice was rated more expert on technology, a female voice on love and relationships (N=40). | "Are machines gender neutral? Gender-stereotypic responses to computers with voices", Journal of Applied Social Psychology, 1997 ([index](https://acnpsearch.tweb-dev.unibo.it/singlejournalindex/7602335)) | abstract; **contested**: the next row did not replicate it |
| A replication with modern text-to-speech voices (N=85) found **no effect of voice gender** on recall, competence, likability or helpfulness. A non-native accent lowered perceived competence, knowledge and helpfulness. | "Voice accentedness, but not gender, affects social responses to a computer tutor", Frontiers in Computer Science, 2024 ([full text](https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2024.1436341/full)) | read |
| Voice assistants trigger implicit gender stereotypes, but trust in a gender-ambiguous voice did not differ from trust in gendered ones (N=234). | "Female by Default? Exploring the Effect of Voice Assistant Gender and Pitch on Trait and Trust Attribution", CHI Extended Abstracts, 2021 ([record](https://www.merlin.uzh.ch/publication/show/21086)) | not checked; extended abstract |
| Voice gender had only small effects on stereotype activation; the conversation topic had none (two studies, N=140 and N=397). | "Gender stereotypes and voice assistants: do users' gender and conversation topic matter?", Behaviour & Information Technology, 2024 ([record](https://ideas.repec.org/a/taf/tbitxx/v43y2024i10p1913-1923.html)) | abstract |
| Both sexes *stated* a preference for female synthetic voices. On implicit measures women preferred them and men showed no bias. | "Does social desirability bias favor humans? Explicit-implicit evaluations of synthesized speech support a new HCI model of impression management", Computers in Human Behavior, about 2011 ([press release](https://scholar.google.com/scholar?q=Does+social+desirability+bias+favor+humans%3F+Explicit-implicit+evaluations+of+synthesized+speech)) | not checked |
| An Italian survey (N=182, four age groups) strongly preferred a high-quality female voice. Quality mattered as much as gender, and the preference vanished when the agents were mute. | "A synthetic voice for an assistive conversational agent: a survey to discover Italian preferences regarding synthetic voices' gender and quality level", Human Behavior and Emerging Technologies, 2023 ([record](https://www.citedrive.com/en/discovery/a-synthetic-voice-for-an-assistive-conversational-agent-a-survey-to-discover-italian-preferences-regarding-synthetic-voices-gender-and-quality-level)) | not checked |
| Listeners still assign a gender to an ambiguous voice, steered by the topic. In Swedish (Chalmers) studies, an ambiguous voice weakened gendering of a robot, and men and women rated ambiguous voices alike. | "Gender Ambiguity in Voice-Based Assistants", Human-Machine Communication, 2022 ([pdf](https://scholar.google.com/scholar?q=Gender+Ambiguity+in+Voice-Based+Assistants%3A+Gender+Perception+and+Influences+of+Context)); "Can a gender-ambiguous voice reduce gender stereotypes in human-robot interactions?", IEEE RO-MAN, 2023 ([record](https://research.chalmers.se/en/publication/539220)); "Hearing Ambiguity: Exploring Beyond-Gender Impressions of Artificial Ambiguous Voices", ACM CUI, 2025 ([record](https://research.chalmers.se/publication/547693)) | not checked / abstract / abstract |
| Female-by-default assistants that answer abuse submissively reinforce stereotypes. The report recommends ending female defaults and having assistants announce they are not human. | "I'd blush if I could: closing gender divides in digital skills through education", UNESCO / EQUALS, 2019 ([page](https://www.equalsintech.org/i-d-blush-if-i-could)) | not checked; a policy report, not a preference study |
| An industry panel rated a synthetic female voice 12.5% higher than a male one (N=240). | "What consumers want in voice app design", Voicebot.ai, 2019 ([pdf](https://voicebot.ai/wp-content/uploads/2019/11/what_consumers_want_in_voice_app_design_voicebot.pdf)) | not checked; not peer-reviewed |

Gaps:

- No meta-analysis of voice gender in synthetic voices was found.
- No Swedish or Nordic data on synthetic voice gender for phone callers was found.

## 2. Other voice parameters

| Parameter | What the evidence says | Source | Strength |
|---|---|---|---|
| First impression | Listeners agree on personality from a sub-second "hello". The judgements fall on two axes: trust and likability, and dominance. The first second of the call counts. | "How Do You Say 'Hello'? Personality Impressions from Brief Novel Voices", PLOS ONE, 2014 ([PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3951273/)) | not checked; widely cited |
| Pitch | The popular "lower pitch reads as more competent" is **contested** for synthetic voices. Changing pitch shifted perceived dominance, not trustworthiness. Speech rate and voice quality predicted trust better. | Comparative trustworthiness study, Computers in Human Behavior Reports, 2025 ([pdf](https://scholar.google.com/scholar?q=comparative+trustworthiness+synthetic+human+voices+pitch+Computers+in+Human+Behavior+Reports+2025)) | not checked |
| Warmth and competence | Listeners hear warmth and competence in commercial text-to-speech voices, and both can be shifted by voice choice. For a salon or clinic, warm *and* competent is the target, not one at the cost of the other. | "Perception of social speaker characteristics in synthetic speech", Interspeech, 2021 ([paper](https://scholar.google.com/scholar?q=Perception+of+social+speaker+characteristics+in+synthetic+speech)) | not checked |
| Consistency | People prefer a voice whose personality matches the words. Keep one voice and one persona for the whole call; don't mix a playful voice with stiff scripted sentences. | "Does computer-synthesized speech manifest personality? Experimental tests of recognition, similarity-attraction, and consistency-attraction", Journal of Experimental Psychology: Applied, 2001 ([press](https://sciencedaily.com/releases/2001/10/011001072153.htm)) | not checked; foundational |
| Accent | Statements read with a foreign accent were rated less true (native 7.5, mild 6.95, heavy 6.84). The proposed cause is processing effort. The 2024 tutor study (§ 1, read) also found a native-accent advantage. | "Why don't we believe non-native speakers? The influence of accent on credibility", Journal of Experimental Social Psychology, 2010 ([record](https://pure.royalholloway.ac.uk/en/publications/why-dont-we-believe-non-native-speakers-the-influence-of-accent-o)) | not checked; **contested** by a 2024 Journal of Cognition study |
| Dialect (Swedish) | No study compares standard Swedish with a regional accent on trust. In a Finland-Swedish survey, warmth was the strongest dimension, and capital-region speech read as more competent but less warm. Practical reading: a voice that sounds native and neutral in Swedish. A foreign-sounding accent from an English-trained voice is the real risk. | "Finlandssvenskars uppfattningar och åsikter om språklig variation – En webbenkät", Folkmålsstudier, about 2015 ([record](https://research.utu.fi/converis/portal/detail/Publication/2205502)); Mid Sweden University project page on accent attitudes ([page](https://epi-prod.miun.se/en/Research/research-projects/ongoing-research-projects/accents-dialects-and-attitudes/)) | not checked |
| Speech rate | Comprehension of phone speech falls with listener age, more so for synthetic speech. Familiar words and context offset it. No firm words-per-minute target for the phone was found. Clinics have many older Callers. | Eurospeech, 2001 ([paper](https://scholar.google.com/scholar?q=Eurospeech+2001+telephone+synthetic+speech+comprehension+older+listeners)); ISCA Speech Synthesis Workshop, 2007 ([paper](https://scholar.google.com/scholar?q=SSW+2007+older+listeners+synthetic+speech+familiar+words)) | not checked |
| Smile voice | Listeners hear smiling above chance and judge it happier; replicated across decades. A mismatched smile or frown slows comprehension. | "Audible smiles and frowns affect speech comprehension", 2012 ([record](https://acuresearchbank.acu.edu.au/item/8634w/audible-smiles-and-frowns-affect-speech-comprehension)) | not checked |
| Expressiveness | Thin and mixed evidence for expressive over neutral synthetic speech. | (several small studies) | not checked |
| Age impression | Nothing usable found. | none | none |

What we can steer: Gemini has no rate, pitch or smile parameter (the Live API pages document none). The voice is chosen from the 30 prebuilt voices listed in `gemini-live-voice-and-language.md` § 3, and the prompt shapes tone. Whether a prompt line such as "speak calmly, at a relaxed pace" changes the native-audio model's rate is not documented; not checked.

## 3. Conversation behaviour

### Latency and turn-taking (the strongest lever)

- **Turn gaps are short everywhere.** Across ten languages the mean gap is about 200 ms, and each language sits within about 250 ms of the mean. Danish, the nearest neighbour sampled, was slowest at about +470 ms; Swedish was not sampled. Source: "Universals and cultural variation in turn-taking in conversation", PNAS, 2009 ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC2705608/)). Read; replicated.
- **Speech takes over 600 ms to plan,** so human listeners predict where a turn ends. Source: "Timing in turn-taking and its implications for processing models of language", Frontiers in Psychology, 2015 ([full text](https://www.frontiersin.org/articles/10.3389/fpsyg.2015.00731/full)). Not checked; a consensus review.
- **A gap of 700 ms or more is heard as a coming "no".** In phone corpora, refusals clearly outnumber acceptances after such gaps. Source: "The timing and construction of preference: a quantitative study", Discourse Processes, 2015 ([eprint](https://eprints.whiterose.ac.uk/116177)). Not checked.
- **About 1 s of silence is the point where people sense trouble.** Source: the conversation-analysis chapter on a "standard maximum" silence of about one second, in "Conversation: An Interdisciplinary Perspective", 1989 ([summary](https://scholar.google.com/scholar?q=Preliminary+notes+on+a+possible+metric+which+provides+for+a+standard+maximum+silence+of+approximately+one+second+in+conversation)). Not checked; a book chapter.
- **People tolerate longer delays from machines, but it costs.** Added delays of a few hundred ms lowered ratings in a socialbot. Higher latency in an LLM agent lowered engagement and perceived competence. A service robot was tolerated up to about 4 s, and satisfaction dropped at 8 s. Sources: "Mitigating Response Delays in Free-Form Conversations with LLM-powered Intelligent Virtual Agents", arXiv, 2025 ([preprint](https://arxiv.org/pdf/2507.22352)); "Athena: Constructing Dialogues Dynamically with Discourse Constraints", arXiv, 2020 ([preprint](https://arxiv.org/pdf/2011.10683)). Not checked; mostly preprints and small samples.
- **A short preface ("let me check") cuts the felt wait.** In a field robot, "preface" openers cut initial latency without lowering ratings. Source: "Low-Latency Turn-Taking via Context-Aware Preface Generation in a Real-World Dialogue Robot", arXiv, 2026 ([preprint](https://arxiv.org/pdf/2607.23204)). Not checked.

Reading for us:

- The gap after the Caller stops is end-of-speech silence plus the model's time to first audio.
- Today's silence is Gemini's server default of about 800 ms (`voice/bargein.py` sets none). That alone passes the 700 ms "sounds like a no" mark before the model has even started.
- Google recommends 500 to 800 ms ([Live API capabilities guide](https://ai.google.dev/gemini-api/docs/live-api/capabilities), read). The first demo used 500 ms.
- So VOI-178 is the single cheapest change with the strongest evidence behind it.
- The cost: too short a silence cuts Callers off in Swedish mid-sentence pauses ("alltså …").

### Opening

- **Swedish callers expect a name.** In Swedish phone openings the answerer greets, then identifies ("Hej, det är X"), much as in Dutch. Source: "Identification and recognition in Swedish telephone conversation openings", Language in Society, 1994 ([record](https://resolve.cambridge.org/core/journals/language-in-society/article/identification-and-recognition-in-swedish-telephone-conversation-openings/E2117620E7A2A55C06173C00055BC76A)). Not checked.
- **Today the first line is only "Du pratar med en AI-assistent."** No greeting, no Business name. A Caller who has just dialled a salon hears neither where they landed nor a greeting. Adding a greeting and the Business's name next to the disclosure fits the norm and does not weaken the disclosure.

### Backchannels ("mm", "okej")

- **Listeners shape how well a story gets told.** Specific, attentive listener responses improved storytelling; distracted listeners spoiled it. Source: "Listeners as co-narrators", Journal of Personality and Social Psychology, 2000 ([PubMed](https://pubmed.ncbi.nlm.nih.gov/11138763)). Not checked.
- **Instant or mistimed backchannels from a system annoy, and read as inattention.** Sources: Eurospeech, 1999 ([paper](https://scholar.google.com/scholar?q=Eurospeech+1999+backchannel+timing+spoken+dialogue+system+user+impression)); Frontiers in Robotics and AI, 2023 ([article](https://www.frontiersin.org/articles/10.3389/frobt.2023.988042)). Not checked.
- **For us:** Gemini's native audio decides when to make sounds, and we can't time them. A soft prompt line ("the odd 'mm' or 'okej' is fine") is the most we should do. Weak evidence either way.

### Confirming understanding

- **Grounding means confirming "well enough for current purposes" at the least joint effort.** Source: "Grounding in communication", in "Perspectives on Socially Shared Cognition", 1991. Not checked; foundational.
- **Explicit confirmation is preferred after an error; implicit confirmation is fine when things go right.** Repeating the same confirmation question annoys. Sources: Interspeech, 2004 ([paper](https://scholar.google.com/scholar?q=Interspeech+2004+explicit+implicit+confirmation+spoken+dialogue+user+preference)); Dialogue & Discourse, 2022 ([paper](https://aclanthology.org/2022.dnd-13.4/)). Not checked; small samples.
- **For us:**
  - Read back costly details explicitly: a time, a date, a number. Once Modules book things, that matters most.
  - For a plain question ("har ni öppet på lördag?"), answer with the fact; "på lördag har vi öppet tio till fyra" confirms implicitly.

### Brevity

- **Broad phone menus beat deep ones,** especially for users with low working memory. Source: "A comparison of broad versus deep auditory menu structures", Human Factors, 2008 ([record](https://stars.library.ucf.edu/facultybib2000/233)). Not checked. It is about menus, not conversation.
- **Google: "keep your responses short and progressively disclose more", and limit questions per turn.** Source: [Live API best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices), read.
- **For us:** the core's "Max 2 sentences per turn" fits. One question per turn is a cheap addition.

### Empathy: helps when brief and real, backfires when it replaces the fix

- **Empathetic chatbot replies can worsen reactions.** Callers push back (reactance), and the bot seems less competent, mostly when a failure is salient. Sources: "Bots with Empathy: Reactance Against Emotion-Aware AI Agents in Customer Service", MIS Quarterly, 2026 ([press release](https://www.usf.edu/business/news/2026/04-20-chatbot-empathy-can-worsen-customer-reactions-usf-study.aspx)); earlier version at SIGHCI, 2022 ([paper](https://aisel.aisnet.org/sighci2022/1)). Not checked.
- **Empathic chatbots raise satisfaction, except when customers are in a hurry.** Source: "Empathic chatbots: A double-edged sword in customer experiences", Journal of Business Research, 2025 ([record](https://research.dial.uclouvain.be/handle/2078.5/271000)). Not checked.
- **Empathy lowered satisfaction when the chat had unexpected transactional elements such as upselling.** Source: "The double-edged sword of artificial empathy" ([record](https://madoc.bib.uni-mannheim.de/68235/)). Not checked; venue not confirmed.
- **For us:** acknowledge once, briefly, only when the Caller voices a problem ("Vad tråkigt, det löser vi"), then give the fact or the next step. No mirroring of feelings, no repeated sympathy, no empathy on a plain question. Most Callers to a salon are in a hurry.

### Apologising and recovery

- **The fix matters most.** Satisfaction with complaint handling depends most on the outcome (the fix), then on courtesy and apology, and little on procedure. Sources: "A meta-analysis of satisfaction with complaint handling in services", Journal of the Academy of Marketing Science, 2010 ([doi](https://doi.org/10.1007/s11747-009-0155-z)); "A meta-analysis of organizational complaint handling and customer responses", Journal of Service Research, 2011 ([doi](https://doi.org/10.1177/1094670510387914)). Abstract; meta-analyses, partly contested on how much weight courtesy carries.
- **Hearing the complaint out and acknowledging it before apologising raised satisfaction.** Source: "Listen to their heart: Why does active listening enhance customer satisfaction after a service failure", International Journal of Hospitality Management, 2021. Not checked.
- **For us:** one apology plus what the Caller can do. The core's fixed refusal sentences say what the agent can't do. They don't say where the Caller can go instead, such as the Business's phone or website. That is a dead end.

### Effort, frustration and escalation

- **Low effort predicts loyalty better than delight.** Source: "Stop Trying to Delight Your Customers", Harvard Business Review, 2010 ([page](https://store.hbr.org/product/stop-trying-to-delight-your-customers/R1007L)). Not peer-reviewed; proprietary data; widely cited, not independently replicated.
- **Disclosing the bot before any failure raises tolerance of its failures.** Callers rate it more sincere. Source: "The impact of prior chatbot identity disclosure on customer tolerance of service failures", 2024 ([doi](https://www.emerald.com/intr/article/doi/10.1108/INTR-11-2023-1073/1302059)). Not checked; venue not confirmed.
- **For us:** a frustrated Caller needs the fact, or a clear way to reach a person (the Business's phone or website), sooner, not more words. Handing over to a human live is out of scope today.

### Closing

- **"Something else" beats "anything else".** In a randomised study in primary care (20 physicians, 224 patients), "Is there *something* else …?" cut unmet concerns by 78% against control; "anything else" did no better than control, and neither made visits longer. Source: "Reducing patients' unmet concerns in primary care: the difference one word can make", Journal of General Internal Medicine, 2007 ([PubMed](https://pubmed.ncbi.nlm.nih.gov/17674111/)). Not checked; a single study in English. Whether "något annat" against "något mer" works the same way in Swedish is untested.
- **For us:** the core has no closing behaviour. A closing line ("Var det något annat jag kan hjälpa till med?") and a short goodbye once the Caller is done is caller wording, Petter's.

## 4. The AI disclosure and trust

- **Disclosing up front cut purchases by over 79.7%.** In a field experiment on outbound *sales* calls to more than 6,200 customers, undisclosed bots sold as well as proficient staff. After disclosure, customers turned curt and rated the bot less knowledgeable and less empathetic. Late disclosure and prior AI experience softened the effect. Source: "Frontiers: Machines vs. Humans: The Impact of Artificial Intelligence Chatbot Disclosure on Customer Purchases", Marketing Science, 2019 ([doi](https://doi.org/10.1287/mksc.2019.1192)). Abstract; a single field study.
  - This is the result that drives "disclose late" advice. For us it is excluded twice over: late disclosure breaks Art. 50(5), and our calls are inbound service, not outbound sales.
- **The effect depends on the setting.** For high-criticality services, disclosure lowered trust. When the bot could not solve the issue, disclosure did no harm and slightly raised retention. Source: "Trust me, I'm a bot – repercussions of chatbot disclosure in different service frontline settings", Journal of Service Management, 2022 ([article](https://www.emerald.com/insight/content/doi/10.1108/JOSM-10-2020-0380/full/html)). Abstract.
- **Disclosing before any failure raises tolerance of failures** (§ 3 above). Not checked.
- **When people prefer a machine: embarrassing topics.** Consumers preferred a chatbot to a person for embarrassing purchases, but only if it was clearly not human. Source: "Avoiding embarrassment online: Response to and inferences about chatbots when purchases activate self-presentation concerns", Journal of Consumer Psychology, about 2024 ([press](https://news.osu.edu/when-consumers-would-prefer-a-chatbot-over-a-person/)). Not checked. Relevant to clinics.
- **Algorithm aversion against algorithm appreciation is contested.** People drop an algorithm after seeing it err, yet laypeople also over-rely on algorithmic advice. Sources: "Algorithm aversion: People erroneously avoid algorithms after seeing them err", Journal of Experimental Psychology: General, 2015; "Algorithm appreciation: People prefer algorithmic to human judgment", Organizational Behavior and Human Decision Processes, 2019 ([page](https://www.hks.harvard.edu/publications/algorithm-appreciation-people-prefer-algorithmic-human-judgment)). Not checked.
- **Google Duplex, 2018:** a human-sounding booking bot that did not say what it was drew wide criticism, and Google then added a disclosure at the start of the call ([MIT Technology Review, 2018](https://www.technologyreview.com/2018/05/11/66887/people-are-freaking-out-about-googles-extremely-human-sounding-phone-call-making/)). News, not checked.
- **Framing gap.** No peer-reviewed study was found that tests whether stating what the agent *can* do, right after the disclosure, softens it. It is plausible and cheap, but an untested idea.

Reading:

- Keep the disclosure first and word for word.
- Make it part of a warm, competent opening (greeting, Business name, what the agent can help with), not a cold first sentence.
- The rest of the call carries trust: speed, accuracy, no dead ends. A Caller primed that it is an AI forgives a miss more readily.

## 5. Swedish specifics

- **"Du" is the official default** for addressing one private person; "ni" is for several people or an organisation. Source: "Du eller ni? Myndigheten eller vi?", Institutet för språk och folkminnen, Klarspråkshjälpen ([page](https://www.isof.se/stod-och-sprakrad/spraktjanster/klarsprakshjalpen/skriv-klarsprak/tank-pa-dina-lasare/fordjupning-tank-pa-dina-lasare/du-eller-ni-myndigheten-eller-vi)). Read.
- **Singular "ni" as a polite form is disputed.** Many Swedes dislike it, and some service firms have brought it back. Sources: [SVT](https://www.svt.se/kultur/darfor-blir-folk-sa-sura-av-att-bli-niade); background on the late-1960s du-reform ([SVT](https://www.svt.se/kultur/experterna-du-reformen-ar-sveriges-storsta-sprakhandelse)). Not checked; press. The core's prompt says neither, which leaves the register to the model. VOI-180 asks Petter to decide.
- **Directness, small talk, lagom:** no peer-reviewed study was found, only practitioner guides ([SBS Cultural Atlas](https://culturalatlas.sbs.com.au/swedish-culture/swedish-culture-communication)). Treat "Swedes dislike small talk and want it short and plain" as folk wisdom. It points the same way as Google's brevity advice and the effort research.
- **Swedish pause data exists but was not extracted:** pauses and gaps in spontaneous Swedish dialogue (Interspeech, 2009, [paper](https://scholar.google.com/scholar?q=Interspeech+2009+pauses+gaps+spontaneous+Swedish+dialogue)) and prosodic cues at Swedish turn ends (Interspeech, 2023, [paper](https://scholar.google.com/scholar?q=Interspeech+2023+prosodic+cues+turn+end+Swedish)). Not checked. Worth reading before picking a silence value under VOI-178.
- **Swedes' views of AI:** "Svenskarna och internet 2025" (Internetstiftelsen, [report](https://svenskarnaochinternet.se/app/uploads/2025/09/internetstiftelsen-svenskarna-och-internet-2025.pdf)) has an AI chapter. Per press, more Swedes expect AI to do harm than good. Commercial surveys on preferring AI or human customer service conflict (about half prefer a human). Not checked. Nothing found on synthetic voices.

## 6. What we control, and how each effect would be measured

| Lever | Where | What it can change | Who decides |
|---|---|---|---|
| Voice | `prebuilt_voice_config.voice_name` (one of 30) | warmth, clarity, gender impression, accent in Swedish | Petter, by ear (VOI-156, VOI-163) |
| System instruction | `system_instruction` in `voice/agent.py` | persona, tone, du, brevity, opening and closing lines, empathy and apology rules | Caller wording is Petter's; eval-required (full paid `make eval`, `evals-approved`) |
| VAD | `VAD` in `voice/bargein.py` | end-of-speech silence (reply speed), start sensitivity (barge-in) | eval-required (VOI-178) |
| Scenarios and checks | `tests/evals/` | evidence that a change holds | a second read before `evals-approved` |

What an eval can show:

- The eval channel plays stored Caller audio against the real agent, so it can check **what** the agent says and **when** it speaks. `tests/evals/run.py` already records the first time to first audio (`ttfb`) per Scenario. It does not yet record the gap before each reply.
- It cannot measure what Callers *feel*. Warmth, trust and voice preference need people: Petter's blind listening (VOI-156), and then real calls.

A real-call A/B would need:

- **Real calls:** callers from a Business that agrees, or numbers we own. Petter decides.
- **A rule on what is stored:** only outcomes, never Callers' words or audio (`.claude/rules/security.md`, the VOI-153 Call log rule).
- **Outcome measures from the call record:** errand completed (a fact given, or an Action that succeeded), call length, hang-ups during or right after the disclosure, the Caller repeating a question, and long silences.
- **Optional:** a one-question rating at the end. That informs callers, so it is Petter's wording.
- **Enough calls per arm to see a difference:** not estimated here. It depends on call volume, which we don't have yet.

## 7. Recommendations, ranked

Ranked by expected effect on Callers per unit of effort, with evidence strength last.

| # | Recommendation | Impact | Effort | Evidence | Ticket |
|---|---|---|---|---|---|
| 1 | Cut the reply gap: end-of-speech silence 500-600 ms, and measure the gap before every reply in the eval report (aim below about 700 ms after the Caller stops, never near 1 s). | high | low | strong: turn-taking universals, the 700 ms "no" signal, Google's range | VOI-178 (comment); new: reply gap in the eval report |
| 2 | A warm, competent opening: greeting, the Business's name, the disclosure word for word, and in one phrase what the agent can help with. | high | low | medium: Swedish phone openings, first-impression study; the framing itself untested | new (caller wording and disclosure: Petter) |
| 3 | Prompt persona and phone tone: one consistent warm, competent persona; "du"; short turns with progressive disclosure; one question per turn; no read-aloud scripts beyond the disclosure. | high | medium | medium: Google best practices, consistency-attraction, brevity | VOI-177 (comment), VOI-180 (du) |
| 4 | Choose the voice by blind listening for warmth and clarity in *Swedish*, not by gender. Include at least one female, one male and one less-gendered candidate, and reject any that sounds foreign in Swedish. | medium | low | strong that gender alone is weak; medium on accent | VOI-156, VOI-163 (comment) |
| 5 | No dead ends: when the agent can't help, one short apology plus where to go instead (the Business's phone or website, from its facts). | medium | low | medium: complaint-handling meta-analyses, effort research (HBR not peer-reviewed) | VOI-143 (comment) |
| 6 | Brief empathy only when a Caller voices a problem, then the fact; never repeated, never on plain questions. Checked by a frustrated-Caller Scenario. | medium | medium | medium, conditional: empathy backfire studies | new Scenario |
| 7 | A holding line before a slow tool call ("Ett ögonblick, jag kollar"), so no silence nears 1 s. | medium | low | medium: 1 s standard maximum, preface study (preprint) | new |
| 8 | A closing: "Var det något annat jag kan hjälpa till med?", then a short goodbye. | low-medium | low | weak for Swedish: one English RCT | new |
| 9 | Read back costly details (times, numbers) explicitly once Modules book things; confirm plain facts implicitly. | medium later | low | weak-medium: dialogue-system studies | VOI-177 (comment) |
| 10 | Spec a real-call A/B with outcome measures (completion, repeats, early hang-ups), storing no Caller words. | high long-term | high | method, not a finding | new spec (real calls: Petter) |

Not recommended:

- Telling the model to add many "mm"s or fillers: Gemini times its own sounds, and mistimed ones annoy.
- Anything that delays or softens the disclosure.

## Not checked

- Most academic sources rest on abstracts or search summaries (marked per row). Effect sizes are rarely given. Re-read a paper before quoting a number.
- Swedish pause and gap measurements (Interspeech 2009 and 2023) were found but their numbers not extracted.
- No Swedish or Nordic data on synthetic voice gender, perceived age, or standard against regional accent on trust.
- Whether a prompt line changes Gemini native audio's speech rate or warmth.
- Whether "något annat" works like "something else".
- The Commission's July 2026 guidelines on Art. 50 were not read. The Omnibus status of Art. 50(1) rests on law-firm notes.
