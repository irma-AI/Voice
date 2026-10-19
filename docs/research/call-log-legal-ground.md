# Legal ground for keeping a call's words and audio

Retrieved 2026-10-19 for VOI-155 (parent spec VOI-152). Question: what must hold for Voice to keep a test call's words and audio for 30 days; who is controller and who processor for a test call made by a Business's staff; what the person pressing the test call button must be told, and when; whether consent or legitimate interest is the ground; and what it would take (not whether to do it) to keep a real Caller's words and audio later.

This is research from official sources, not legal advice. Facts no official source confirmed are marked "not checked".

## Sources

| Source | Link | Read |
|---|---|---|
| GDPR, Regulation (EU) 2016/679, consolidated English text from the EU Publications Office (the store behind EUR-Lex; the EUR-Lex page itself answered with a bot challenge, so the same CELEX document was fetched from the Publications Office) | https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng, fetched as http://publications.europa.eu/resource/celex/32016R0679 | 2026-10-19 |
| Brottsbalken (1962:700) 4 kap. 8, 9 a, 9 b §§, riksdagen.se, text "t.o.m. SFS 2026:1656" | https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/brottsbalk-1962700_sfs-1962-700/ | 2026-10-19 |
| IMY, Personuppgiftsansvariga och personuppgiftsbiträden (updated 15 June 2026) | https://www.imy.se/verksamhet/dataskydd/det-har-galler-enligt-gdpr/personuppgiftsansvariga-och-personuppgiftsbitraden/ | 2026-10-19 |
| IMY, Samtycke (updated 15 June 2026) | https://www.imy.se/verksamhet/dataskydd/det-har-galler-enligt-gdpr/rattslig-grund/samtycke/ | 2026-10-19 |
| IMY, Intresseavvägning (updated 15 June 2026) | https://www.imy.se/verksamhet/dataskydd/det-har-galler-enligt-gdpr/rattslig-grund/intresseavvagning/ | 2026-10-19 |
| IMY, Arbetsliv: Rättslig grund (updated 15 June 2026) | https://www.imy.se/verksamhet/dataskydd/dataskydd-pa-olika-omraden/arbetsliv/tillaten-behandling--vilka-krav-galler/rattslig-grund/ | 2026-10-19 |
| IMY, När ska en konsekvensbedömning genomföras? (updated 15 June 2026) | https://www.imy.se/verksamhet/dataskydd/det-har-galler-enligt-gdpr/konsekvensbedomning/nar-ska-en-konsekvensbedomning-genomforas/ | 2026-10-19 |
| EDPB Guidelines 07/2020 on the concepts of controller and processor, v2.1 | https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-072020-concepts-controller-and-processor-gdpr_en | 2026-10-19 |
| EDPB Guidelines 05/2020 on consent, v1.1 | https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-052020-consent-under-regulation-2016679_en | 2026-10-19 |
| EDPB Guidelines 1/2024 on Article 6(1)(f), v1.0 (the version for public consultation, adopted 8 October 2024; no final version was linked from the page) | https://www.edpb.europa.eu/our-work-tools/documents/public-consultations/2024/guidelines-12024-processing-personal-data-based_en | 2026-10-19 |
| EDPB Guidelines 02/2021 on virtual voice assistants, v2.0 | https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-022021-virtual-voice-assistants_en | 2026-10-19 |

IMY has no page on recording phone or web calls: its site search for "inspelning av samtal", "spela in samtal" and "ljudupptagning" returned only camera surveillance and publishing pages (2026-10-19). So no IMY guidance specific to call recording is cited here: not found.

## 1. What a test call's words and audio are, legally

- A recording of someone's voice, and a transcript of what they said, are personal data: information relating to an identifiable person (GDPR Art. 4(1)). Storing them is processing (Art. 4(2) lists "recording" and "storage").
- Voice is not automatically special-category data. Art. 9(1) covers "biometric data for the purpose of uniquely identifying a natural person"; Art. 4(14) defines biometric data by "specific technical processing" that allows or confirms unique identification. The EDPB says voice data is "inherently biometric personal data" but that Art. 9 applies when it is processed to uniquely identify someone, or when its content is special-category (Guidelines 02/2021, para. 31). Voice keeps audio to hear echo, not to identify speakers, so Art. 9 is not triggered by the purpose. What the person says could still reveal health or similar data; a test call is a staged call, which keeps that unlikely, not impossible.
- On a speakerphone, anyone else in the room is also recorded. They are data subjects too, and they never see the notice (§ 3, § 6).

## 2. Who is controller and who is processor

- The controller "determines the purposes and means" (Art. 4(7)); the processor processes "on behalf of the controller" (Art. 4(8)). The EDPB: a processor "does not process the data for its own purposes" (07/2020, para. 55); a cloud provider stays a processor only "insofar as" it does not process for its own purposes (cloud storage example, p. 13). IMY says the same: the controller is the organisation that decides the purposes and how.
- A processor that decides purposes and means itself "shall be considered to be a controller in respect of that processing" (Art. 28(10)).
- **Keeping a test call's words and audio for 30 days: Voice is the controller.** The purpose is Voice's own (finding why the agent cuts itself off on a speakerphone, VOI-152), Voice decides what is kept, how long and who reads it (Petter only). No Business instructed it. Voice cannot present this as processing on the Business's behalf: under Art. 28(10) it would be a controller anyway.
- **The live test call itself** (audio streamed through the core to Google and back) is the same processing as any call; docs/privacy/README.md § 1 already treats the Business as controller toward its Callers and Voice as processor. For a test call the speaker is the Business's own staff, testing a service the Business buys; whether the Business is controller for that live part or Voice is (as for the staff member's account data) is not settled by any source read: not checked. It does not change the answer for the kept copy, which is Voice's.
- **Google** stays a processor for the live call (Gemini API Paid Services under Google's processor DPA, docs/research/gemini-api-data-terms.md § 3). The kept copy lives in the Portal's Postgres at HostUp; HostUp's terms and server location are still not read (docs/privacy/README.md § 6).
- Joint control (Art. 26) would apply only if Voice and the Business decided the purpose together; nothing in the spec has the Business decide anything about the kept copy, so joint control does not fit (reasoning from Art. 26(1), not from a source on this case).
- **The controller's legal identity**: the notice must name the controller and its contact details (Art. 13(1)(a)). The repository does not say which legal person runs Voice: not checked.

## 3. What the person pressing the test call button must be told, and when

When data is collected from the person themselves, the controller provides the Art. 13 information "at the time when personal data are obtained" (Art. 13(1)), so: on the test call page, before the call starts. Art. 12(1) asks for "concise, transparent, intelligible and easily accessible form, using clear and plain language". Art. 13 lists, among others:

- who the controller is and how to reach it (13(1)(a));
- the purpose and the legal basis (13(1)(c)); for legitimate interest, the interest itself (13(1)(d));
- recipients (13(1)(e)): Google for the live call; the hosting provider for the stored copy;
- transfers outside the EEA and the safeguard (13(1)(f)): Google's DPA rests on standard contractual clauses (gemini-api-data-terms.md § 3);
- how long it is kept (13(2)(a)): 30 days;
- the rights to access, erasure and to object (13(2)(b)); the right to complain to IMY (13(2)(d)).

A short notice beside the button plus a link to a full privacy notice covers this in layers; that layering is common practice, but no source read here was checked for it: not checked. **Voice has no privacy notice of its own yet** (only the Business's notice is linked on the call page, docs/privacy/README.md § 1), so the short notice has nothing to link to; that is a gap (§ 6).

Under legitimate interest the right to object (Art. 21(1)) must be "explicitly brought to the attention of the data subject" at the latest at the first communication, presented "clearly and separately from any other information" (Art. 21(4)). So the notice gives the right to object its own line. IMY's employment page says the same: the employee is told of the right to object at the latest when the data is collected, and of the legitimate interest.

Brottsbalken 4 kap. 9 a § punishes recording "i hemlighet" (in secret) speech in a conversation that the recorder "själv icke deltager i". A test call recorded after a visible notice is not secret, and the agent run by Voice is one side of the conversation; whether an AI agent run by an operator counts as the operator taking part is not settled by the statute text, and no case law or preparatory work was read: not checked. 4 kap. 8 § (telehemlighet) covers getting hold of a message that a post or telecom company carries in an electronic communications network; Voice keeping its own end of a call it runs is a different act, but whether Voice counts as such a company under that section was not checked. Bystanders on a speakerphone are the exposed case: their speech reaches the recording without notice to them; the notice should ask the tester to call where only they are heard (§ 7).

## 4. Consent or legitimate interest

**Consent (Art. 6(1)(a)) fits poorly.**
- Consent must be freely given; it is not if a service is made conditional on consent to processing the service does not need (Art. 7(4), recital 43). If the test call button always records, consent to the recording is bundled with using the button. IMY: consent must be a real choice, the person "ska alltid kunna säga nej", and withdrawing it must be as easy as giving it.
- The tester is often an employee told by their employer to try the agent. The EDPB says an imbalance of power "also occurs in the employment context" (05/2020, para. 21), and IMY says consent cannot be relied on where power is unequal. The imbalance is employer to employee, not Voice to employee, so this is a weaker point than the bundling one; it still makes a refusal less free in practice.
- Consent would need a separate active choice per call (no pre-ticked box, IMY), records of who consented (Art. 7(1)), and deletion on withdrawal.

**Legitimate interest (Art. 6(1)(f)) fits, if Voice does the three steps and writes them down.** The EDPB names three cumulative conditions: a legitimate interest, the processing being necessary for it, and the person's interests not overriding it; the assessment is to be done and documented before the processing starts (1/2024, executive summary). IMY: the interest must be clearly stated; if the same result can be reached in a less privacy-intrusive way, legitimate interest cannot be used; and the assessment should be documented.

1. Interest: finding and fixing faults in the service the tester is testing (the agent cutting itself off on a speakerphone). It is lawful, specific and present (VOI-152 has the failing calls).
2. Necessity: VOI-152 already logs scores and levels for every call; words and audio are added for test calls because hearing the echo is what scores cannot show. That argument has to be written into the assessment; a reviewer could ask whether a shorter clip around each barge-in would do (data minimisation, Art. 5(1)(c)). Not decided here.
3. Balance: test calls are staged by people who chose to test the agent; the call is announced before it starts; only Petter reads words and audio; the database refuses them for any call that is not a test call (VOI-152); kept 30 days, then deleted by one job. Reasonable expectations (recital 47; EDPB 1/2024 lists them as a factor) are met by the notice before the call. The weak spot is bystanders on a speakerphone.

The right to object (Art. 21(1)) then applies: Voice must stop unless it shows compelling grounds. A plain way to honour that is to delete a kept test call on request, or to let the tester start a test call that keeps nothing. Which one is a product choice for Petter.

**Proposed (Petter confirms, Aref checks): legitimate interest, with a written assessment before VOI-160 ships, the notice before the call, and a way to object.**

## 5. What must hold to keep a test call's words and audio for 30 days

1. A written legitimate interest assessment (the three steps in § 4) before the first kept test call.
2. A notice on the test call page before the call starts (§ 3), with a link to a Voice privacy notice that holds the full Art. 13 list. Both are caller-facing wording, so Petter decides them.
3. A way to object: deletion on request, or a test call that keeps nothing.
4. Storage limitation: 30 days, enforced by the store (VOI-157), not by a promise (Art. 5(1)(e); EDPB 02/2021 para. 95: a retention period per data set and purpose).
5. Access limited to Petter; agents never read words or audio (VOI-152); security under Art. 32 (Art. 5(1)(f)).
6. An entry in Voice's record of processing activities (Art. 30): whether Voice is exempt under Art. 30(5) was not checked.
7. A DPIA (Art. 35): IMY says one is required as a rule when at least two of the nine criteria in its Art. 35(4) list are met. The list itself was not read: not checked. A small number of staged test calls, read by one person, seems unlikely to reach two criteria, but that is not confirmed.

## 6. What it would take to keep a real Caller's words and audio later

Listed so the cost is visible; nothing here is built or proposed for building (VOI-152, Out of Scope).

- **Whose purpose decides the controller.** If the Business wants recordings (quality, disputes), the Business is controller and Voice its processor: an Art. 28 processing agreement must cover it (that agreement does not exist yet, docs/privacy/README.md § 6), with recording as a documented instruction (Art. 28(3)(a)). If Voice wants them for its own purpose (debugging, improving the agent), Voice is controller for that purpose (Art. 28(10)) and needs its own basis and its own notice to Callers; the EDPB treats "improvement" as a purpose separate from executing the request, needing its own legal basis (02/2021, paras. 67-68).
- **A legal basis for the Caller's data**: legitimate interest with a written assessment as in § 4, or consent. A Caller cannot see an assessment; their reasonable expectation when phoning a business is the deciding factor (recital 47), not checked for this use.
- **Telling the Caller before they speak** (Art. 13(1) "at the time"): on the call page and, for a phone Channel, spoken at the start. That is caller-facing wording and touches the AI disclosure line (Petter decides both).
- **Brottsbalken 4 kap. 9 a §**: no secret recording, so the notice comes first; whether the agent makes the Business or Voice a participant is not checked (§ 3).
- **Other people in the call**: a Caller on a speakerphone or in a car may carry other voices; they are data subjects without notice.
- **Special-category content**: a real Caller may mention health or similar (a clinic's patients, say); Art. 9 then needs an exception, likely explicit consent, for the stored copy. Not checked for any specific Business type.
- **A DPIA** is likelier for real Callers (volume, new technology, voice): not checked against IMY's list.
- **Retention per purpose, deletion through one path, access control, and rights requests**: finding one Caller's recording on an access request needs a way to identify which calls are theirs, which Voice deliberately does not have; how to answer such a request is open.
- **Sub-processors**: Google already gets the audio live and keeps 55 days; a stored copy adds HostUp (location not read) to what the Business must list.

## 7. Proposed test call notice (PROPOSAL, awaiting Petter)

Caller-facing wording: CLAUDE.md § Stop and ask, Legal wording. Not to be used until Petter approves it on a card in VOI-160, and Aref has checked it.

Swedish:

> Det här är ett testsamtal. Vi sparar det du säger, och det agenten säger, som ljud och text i 30 dagar för att hitta och rätta fel i tjänsten. Bara Voice-teamet kan läsa och lyssna. Ring där bara du hörs.
>
> Du kan när som helst invända: be oss radera samtalet, eller ring ett testsamtal som inte sparas.
>
> Läs mer i vår integritetspolicy.

English:

> This is a test call. We keep what you say, and what the agent says, as audio and text for 30 days to find and fix faults in the service. Only the Voice team can read and listen to it. Call where only you can be heard.
>
> You can object at any time: ask us to delete the call, or make a test call that is not kept.
>
> Read more in our privacy notice.

"Voice-teamet" / "the Voice team" stands in for the controller's name, which is not checked (§ 2). "Privacy notice" links to a Voice privacy notice that does not exist yet. The second paragraph is the Art. 21(4) line and assumes a test call that keeps nothing exists; if Petter picks deletion on request only, it shrinks to that.

## 8. Open points

- Jobylon routes legal questions to Aref Abedi (CEO): the controller analysis (§ 2), the choice of legitimate interest (§ 4) and the notice (§ 7) should get his check before VOI-160 ships. This file is research, not legal advice.
- The legal person behind Voice, for the notice and the privacy policy: not checked.
- A Voice privacy notice (Art. 13 in full) for Business staff and test callers: does not exist.
- The legitimate interest assessment in writing (§ 4): not written.
- IMY's Art. 35(4) list, to decide whether test calls need a DPIA: not read.
- Brottsbalken 4 kap. 8 § and 9 a § for an AI agent run by an operator: statute text only; no preparatory work or case law read.
- EDPB Guidelines 1/2024 were read in their consultation version; a final version was not found on the page.
- Whether the Business or Voice is controller for the live part of a test call: not settled (§ 2).
