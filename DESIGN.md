---
name: Voice
description: A dark, precise instrument for one live call. Blue hour ground, Foam type, one warm light on what is live.
colors:
  blue-hour: "#1A2A44"
  deep-sea: "#0B1322"
  cable-light: "#F5D9A8"
  foam: "#FFFFFF"
  foam-muted: "rgb(255 255 255 / 0.72)"
  foam-faint: "rgb(255 255 255 / 0.5)"
  granite: "#3A3F47"
typography:
  display:
    fontFamily: "Instrument Serif, Georgia, serif"
    fontSize: "clamp(3.25rem, 6.4vw, 5.75rem)"
    fontWeight: 400
    lineHeight: 0.98
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Instrument Serif, Georgia, serif"
    fontSize: "clamp(2.25rem, 4.2vw, 3.5rem)"
    fontWeight: 400
    lineHeight: 1.05
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Instrument Serif, Georgia, serif"
    fontSize: "2.25rem"
    fontWeight: 400
    lineHeight: 1.1
    letterSpacing: "-0.01em"
  title-sm:
    fontFamily: "Instrument Serif, Georgia, serif"
    fontSize: "1.75rem"
    fontWeight: 400
    lineHeight: 1.15
  spoken:
    fontFamily: "Instrument Serif, Georgia, serif"
    fontSize: "1.625rem"
    fontWeight: 400
    lineHeight: 1.15
  note:
    fontFamily: "Instrument Serif, Georgia, serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.2
  lede:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.5
  body:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  small:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.12em"
rounded:
  md: "0.5rem"
  pill: "9999px"
spacing:
  unit: "0.25rem"
  gutter: "clamp(1.25rem, 5vw, 4rem)"
  section: "5rem"
  measure: "90rem"
components:
  button-primary:
    backgroundColor: "{colors.foam}"
    textColor: "{colors.deep-sea}"
    typography: "{typography.small}"
    rounded: "{rounded.pill}"
    padding: "0.625rem 1.25rem"
  button-primary-hover:
    backgroundColor: "{colors.cable-light}"
    textColor: "{colors.deep-sea}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.foam-muted}"
    typography: "{typography.small}"
    rounded: "{rounded.pill}"
    padding: "0 1.125rem"
    height: "2.75rem"
  button-ghost-hover:
    textColor: "{colors.foam}"
  link-text:
    textColor: "{colors.foam-muted}"
    typography: "{typography.small}"
  link-text-hover:
    textColor: "{colors.foam}"
  nav-link:
    textColor: "{colors.foam-muted}"
    typography: "{typography.small}"
  input-text:
    backgroundColor: "{colors.deep-sea}"
    textColor: "{colors.foam}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0.625rem 0.75rem"
  mark-today:
    textColor: "{colors.cable-light}"
    typography: "{typography.label}"
  mark-module:
    textColor: "{colors.foam-muted}"
    typography: "{typography.label}"
  mark-planned:
    textColor: "{colors.foam-muted}"
    typography: "{typography.label}"
---

# Design System: Voice

The tokens' one source is `portal/static/portal/tokens.css` (a Tailwind `@theme` block); the core's call page holds a copy kept equal by `tests/test_design_tokens.py`. The frontmatter above mirrors that file as built on 2026-10-18. When they differ, `tokens.css` wins and this file is stale.

## Overview

**Creative North Star: "The Instrument at Blue Hour"**

Voice is drawn as a precise instrument seen at dusk: a dark sea-blue ground, white type, hairline geometry, and one warm light that marks only what is live. The landing page's Turn ring is the first expression: one call drawn as it happens, time filling a ring, each step the agent takes landing on it as a hollow dot. The system is calm and spare, with large serif words and small tracked sans labels. Depth comes from the ground's tonal falloff, never from cards, shadows or glow.

The brand direction (Nordic minimalism, luxury, reliable, natural conversation) rules out the generic AI startup look (glowing orbs, decorative gradients), call-centre and developer-tool styling, mascots, retro and playful treatments.

**Key Characteristics:**
- Dark ground: Deep sea under a Blue hour radial falloff, fixed to the viewport.
- One warm accent, Cable light, reserved for live state and focus.
- Serif for what is said and headlined; sans for interface and labels.
- Hairlines, ticks and small hollow dots instead of boxes.
- Status shown by dot fill: filled is working, hollow is with a Module, dashed is Planned.

## Colors

A near-monochrome night palette with one warm light.

### Primary
- **Cable light** (`cable-light`): the one warm accent. Used only on what is live or active: the progress arc and step dots, the Agent's spoken words and speaker line, step notes, the "Works today" mark, focus rings, text selection, input caret, and the primary pill's hover.

### Neutral
- **Deep sea** (`deep-sea`): the deepest ground and the body background; also the fill inside hollow dots and the text on Foam pills.
- **Blue hour** (`blue-hour`): the lighter ground, used as the top of the body's radial falloff (`radial-gradient(120% 90% at 70% 0%, blue-hour 0%, deep-sea 78%)`).
- **Foam** (`foam`): headlines, spoken Caller lines, body text, and the primary pill.
- **Foam muted** (`foam-muted`, Foam at 72%): secondary text, ledes, nav links, labels, form labels.
- **Foam faint** (`foam-faint`, Foam at 50%): control borders (inputs, ghost button), link underlines, and everything Planned.
- **Granite** (`granite`): hairline rules, the ring and rail track. About 1.7:1 on Deep sea, so it is for decorative lines only, never for a control border.

### Named Rules
**The Live Light Rule.** Cable light marks only what is live, active or focused. A line that has finished speaking goes back to Foam; a Planned thing never gets Cable light.

**The Faint Border Rule.** A border that bounds a control uses Foam faint, not Granite; Granite is too low-contrast to define an interactive edge.

## Typography

**Display Font:** Instrument Serif (with Georgia, serif)
**Body Font:** Geist, variable (with system-ui, sans-serif)

**Character:** a tall, high-contrast serif carries headlines and spoken words; a clean geometric sans carries interface text and small tracked labels. Both are self-hosted stand-ins (SIL OFL 1.1) until the final faces are chosen.

### Hierarchy
- **Display** (400, fluid 3.25 to 5.75rem, 0.98): the one page headline.
- **Headline** (400, fluid 2.25 to 3.5rem, 1.05, max 20ch): section headings.
- **Title** (400, 2.25rem, 1.1): sub-section heads such as Hosted and Self-hosted; Portal page h1s use 3rem today.
- **Title small** (400, 1.75rem, 1.15): list-row heads in the use list.
- **Spoken** (400 serif, 1.625rem on phones, 28 units inside the ring): the words of the call, Caller in Foam, Agent in Cable light.
- **Note** (italic serif, about 17px): the short note under a step name.
- **Lede** (1.125rem, 1.5, 34 to 52ch): sublines and section introductions in Foam muted.
- **Body** (1rem, 1.5): running text.
- **Small** (0.875 to 0.9375rem): nav links, text links, pill labels, captions.
- **Label** (500, 0.75rem, 0.12em, uppercase): speaker names (Caller, Agent), step names, status marks, and the "Portal" suffix beside the wordmark.

### Named Rules
**The Said in Serif Rule.** Words spoken in a call and headings are serif; anything you operate or scan as data is sans.

**The Label Is Data Rule.** The uppercase tracked label names a speaker, a step or a status. It never sits above a heading as a kicker or eyebrow.

## Layout

Every band (nav, hero, sections, footer) shares one measure of 90rem centred, with a side gutter that grows from 1.25rem to 4rem. Sections open with 5rem top padding; the footer sits 7rem below the last section. The hero is a two-column grid (0.9fr text, 1.1fr instrument) at least one viewport tall.

At 860px and below the layout goes to one column: wide-only nav links hide, the ring becomes a vertical rail down the right edge (track, warm fill downward, the same dots), and the current step and line sit in a block under the actions. Lists that were three columns (head, description, mark) stack, with the mark below.

Prose is held to a measure: 34ch for the hero subline, 40ch for the two-way columns, 52ch for ledes.

## Elevation & Depth

Flat. There are no shadows, cards or raised surfaces. Depth is the ground itself: the Blue hour falloff at the top right sinking to Deep sea. Separation is done with 1px Granite hairlines (rows, section rules, footer rule), never with fills.

**The No-Lift Rule.** Nothing casts a shadow or glows. If a thing needs to stand out, it gets Cable light or the Foam pill, not elevation.

## Shapes

Two corner shapes: the full pill for actions and toggles, and a gentle 0.5rem radius for text fields. Everything else is square-edged or drawn as line: 1px hairlines, ticks (120 around the ring, every tenth longer and lighter), and small hollow circles with a 2px stroke. A dashed stroke means Planned, both on dots and on the exit line that leaves the ring.

## Components

### Buttons
- **Primary pill:** Foam ground, Deep sea text, 500 weight, pill shape; warms to Cable light on hover; focus ring offset 4px. One primary action per band.
- **Ghost toggle:** transparent pill with a 1px Foam faint border and Foam muted text, at least 2.75rem tall; on hover the text goes Foam and the border Foam muted. Used for the Pause/Play control and the Portal's secondary actions.

### Links
- **Text link:** Foam muted, underlined with a 0.3em offset and a Foam faint underline that turns Cable light on hover; text goes Foam on hover. "Open code · Self-host it" is the pattern.
- **Nav link:** Foam muted small text, no underline, Foam on hover.

### Inputs / Fields
- **Style:** full width, Deep sea at 60% fill, 1px Foam faint border, 0.5rem radius, Foam text, Cable light caret.
- **Hover / Focus:** border goes Foam muted on hover and Cable light on focus. Checkboxes take Cable light as accent colour.

### Status marks
A label with a small dot before it. Works today: Cable light text and filled dot. With a Module: Foam muted text, hollow Cable light dot. Planned: Foam muted text, dashed Foam faint dot.

### Use list
A borderless list ruled by Granite hairlines: serif row head, Foam muted description, status mark right-aligned.

### Saved notice and call preview
The saved notice is Foam text after a filled Cable light dot (it marks a live change). The settings page's call preview is the one bounded panel in the Portal: a Foam panel with Deep sea text holding the Business's logo, a ring mark and the button in the adjusted accent, because it stands in for a panel on the Business's own website. It shows the Theme as saved.

### Turn (signature)
The call drawn as an instrument. Ring: Granite track, 120 ticks, Cable light progress arc filling clockwise over the loop, a hollow dot per step with a sans label and an italic serif note; a Planned step leaves by a dashed exit. Inside: a speaker line that is flat in silence, Foam for the Caller and Cable light for the Agent, with the current line and the previous one at 55% opacity. Phones: the rail described under Layout. It always has a Pause control, and under reduced motion it starts paused on one complete still frame. Steps and lines fade in over 1 to 1.2s on a soft ease-out.

## Do's and Don'ts

### Do:
- **Do** keep Cable light for live state, active steps, the Agent's words and focus (The Live Light Rule).
- **Do** separate with 1px Granite hairlines and keep surfaces flat on the Deep sea ground.
- **Do** bound controls with Foam faint, not Granite.
- **Do** mark unbuilt capability with the dashed Planned treatment.
- **Do** give any moving element a visible Pause control and a still frame under reduced motion.

### Don't:
- **Don't** add shadows, glows, cards or photos.
- **Don't** use a gradient as decoration; the only gradient is the ground's Blue hour falloff.
- **Don't** put the uppercase label above a heading as a kicker or eyebrow.
- **Don't** colour a finished or Planned thing in Cable light.

## Open

- Final typefaces and their licences; Instrument Serif and Geist are stand-ins.
- The light daylight variant of the palette for the Portal on phones: declined in VOI-86 (see DECISIONS.md); needs a measured palette first.
- WCAG 2.2 AA contrast has not been checked across the whole palette; only Granite as a control border was measured and ruled out.
- Error and alert colours have no token yet.
