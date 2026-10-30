# Kiboko Core Loop Video Series

As of Oct 23, 2026

## How to use this doc

There are six videos: an intro, then one per core loop step (See, Propose, Score, Execute, Prove). Each video section has two parts: a **browser prompt** you paste into Claude in Chrome, and a **narration script** you paste into ElevenLabs. Record the screen silently, generate the voice separately, then line the two up in your editor.

### Recording setup

1. Start Kiboko and log in as an executive user before recording, so no login screen appears in the videos.
2. Size the Chrome window to 1920 x 1080 (or 1440 x 900 on a laptop) and set page zoom to 100%.
3. Open the Claude in Chrome side panel. It sits beside the page, so record only the page area: press Cmd+Shift+5, choose **Record Selected Portion**, and drag the frame over the browser viewport, leaving out the side panel, tabs and address bar.
4. Turn off notifications (Focus mode) and hide the Dock.
5. Start recording, then send the prompt. Stop when Claude reports it has finished the final hold.

### Pacing conventions

- Each prompt tells Claude to **hold** for a set number of seconds at each scene. The holds are sized to the narration for that scene, so the edit is mostly trimming.
- Narration scripts are split into scenes that match the prompt's scenes one to one. Scene numbers appear in both.
- Trim the dead time between scenes in your editor (iMovie, ScreenFlow, Descript), then lay the audio over it.

### ElevenLabs settings

- Model: **Eleven Multilingual v2**. It supports the `<break time="1.0s" />` pause tags used in the scripts (max 3 seconds each).
- Voice settings: stability around 50%, similarity around 75%, style 0 to 15%. Calm and confident, not salesy.
- Generate one scene at a time. A bad take then costs one scene, not a whole video.
- The scripts spell numbers the way they should be spoken (for example, "eighty-two" rather than "82").
- Paste only the narration text, without the leading `>` quote marker.

## Video 0: Intro, what Kiboko is

The intro runs about four minutes with two voices. The **primary voice** introduces each screen in one or two sentences. Then a second **guide voice** explains what the viewer should take from that screen and how to use it. Start on any Kiboko page with Company = Home Products Company applied, logged in as `admin`.

### Fixes from the Oct 23 test recording

- **Login:** the take was logged in as `method`, who isn't a voter, so Score Projects showed "0 awaiting your score". Log in as `admin` to get the four-project queue. If you keep that take, use the alternate scene 5 line below.
- **Pre-roll:** the first 20 seconds sit on the Help page. Trim them, or start the prompt from the Pipeline page.
- **Claude in Chrome overlay:** the "Stop Claude" button at the bottom centre and the orange border around the page are in every frame. Crop them out in your editor, or frame the recording just inside the border.
- **Holds:** the holds below are sized for both voices. The test take's holds were too short for scenes 1 to 7 (see the timing table).

### Timing

Estimates assume about 150 words a minute, a 1-second lead-in and a 1.5-second gap between the two voices.

| Scene | Screen | Test take (s) | Primary (s) | Guide (s) | Needed (s) |
| --- | --- | --- | --- | --- | --- |
| 1 | Pipeline, top | 18 | 12 | 18 | 32 |
| 2 | Pipeline, Revenue chart | 20 | 10 | 20 | 33 |
| 3 | Performance Storyboard | 28 | 9 | 20 | 32 |
| 4 | Project Intake Form | 21 | 6 | 19 | 28 |
| 5 | Score Projects | 21 | 8 | 17 | 28 |
| 6 | Kanban | 12 | 6 | 16 | 24 |
| 7 | Realized Performance | 18 | 9 | 16 | 27 |
| 8 | Pipeline, close | 55 | 9 | 11 | 22 |

### Browser prompt

```text
You are driving Kiboko at http://localhost:8082 for a screen recording.

Rules:
- Move slowly and deliberately. One action at a time.
- After each scene, hold completely still for the stated time (use a wait action; no scrolling or clicking during a hold).
- Wait for every chart to finish rendering before a hold starts.
- Never click Save, Submit, Approve, Delete or Log Out. Never drag Kanban cards. Never open Settings pages, /admin, or any file.
- If a page doesn't match these instructions, stop and tell me instead of improvising.
- Before scene 1: confirm the top bar shows Company = Home Products Company and Business Unit = All Business Units. If not, set them, click Apply, and wait for the page to reload.

Scene 1: Go to http://localhost:8082/app/ (Project Pipeline Value). Scroll to the very top. Hold 32 seconds.
Scene 2: Scroll down slowly until the "Revenue" chart and its summary (Actual, Trending Forecast, Prorated Projected Value, Budget, Delta to Budget) fill the screen. Hold 33 seconds.
Scene 3: In the sidebar, expand Analytics and click Performance Storyboard. Hold 8 seconds on the Brief view. Then click the "Detail" button at the top right of the table (next to "Brief") so the expanded rows appear. Hold 24 seconds.
Scene 4: Click the purple "Add Project" button in the sidebar. Hold 28 seconds.
Scene 5: In the sidebar under Project Prioritization, click Score Projects. Hold 28 seconds.
Scene 6: In the sidebar under Project Control, click Kanban. Hold 24 seconds.
Scene 7: Go to http://localhost:8082/project/19/#realized and scroll so the "Realized Performance" panel and its verdict banner are on screen. Hold 27 seconds.
Scene 8: Go back to http://localhost:8082/app/ and scroll to the top. Hold 22 seconds.
Then tell me "Recording complete".
```

### Narration

Generate the primary and guide lines with two different ElevenLabs voices. In the edit, play the primary line first, leave about a 1.5-second gap, then the guide line. The guide voice works best a little slower and more conversational: stability around 60%, style 0%.

**Scene 1** (Project Pipeline Value)

Primary:

> Every eCommerce team has more ideas than it has time to build. <break time="0.6s" /> So which one goes next? And once it ships, did it actually work? <break time="0.8s" /> Kiboko answers both questions.

Guide:

> This is Project Pipeline Value, the executive home screen. Each tile across the top is one of this year's objectives, with the number of projects behind it and the value they're expected to add. Use the Period buttons to switch between month, quarter and year.

**Scene 2** (Revenue chart)

Primary:

> Kiboko is a RevOps platform for eCommerce. It turns your store analytics into a prioritized, defensible project pipeline, and then tracks whether the work moved revenue.

Guide:

> The Revenue chart shows sales to date in dark green, the trending forecast for the rest of the month in light green, and the budget line above. <break time="0.4s" /> Delta to Budget, on the right, is the gap still to close. Here it's in red, so the team needs more from the pipeline.

**Scene 3** (Performance Storyboard)

Primary:

> It isn't another analytics dashboard, and it isn't a project tool. It sits between the two, as one connected loop. <break time="0.5s" /> Step one: see.

Guide:

> The Performance Storyboard turns the numbers into sentences. Each row shows the current period, the percent change, and what it means in plain English. <break time="0.4s" /> Click Detail, at the top right, to open every supporting metric. The bottom line tells you how total sales moved, here up four point three percent.

**Scene 4** (Add Project)

Primary:

> Step two: propose. Anyone can submit a project, and Kiboko estimates the revenue it could add.

Guide:

> New ideas start here. Fill in the project details on the left: a name, a user story, what done looks like, the objective and the business unit. <break time="0.4s" /> That unlocks the Impact estimator on the right, where you pick the one lever the project moves and set a target.

**Scene 5** (Score Projects)

Primary:

> Step three: score. A team vote and the math combine into one score, so the strongest ideas rise to the top.

Guide (recorded as `admin`, queue showing):

> Score Projects is each person's voting queue. Every project waiting on you appears with its estimate, and you rate it on five criteria with sliders. <break time="0.4s" /> The summary at the top shows how many are waiting, and how much value is at stake.

Guide (alternate, for the Oct 23 take with the empty queue):

> Score Projects is each person's voting queue. When a project is ready, it shows up here with its estimate, and you rate it on five criteria with sliders. <break time="0.4s" /> This user's queue is empty, so nothing is waiting on their vote right now.

**Scene 6** (Kanban)

Primary:

> Step four: execute. Approved work moves from intake to approval to delivery, in one place.

Guide:

> Each column is a stage, from Ready to Score through On Deck to WIP. <break time="0.4s" /> Every card shows its score out of a hundred and its projected value, and the totals at the top show the value sitting in each stage.

**Scene 7** (Realized Performance)

Primary:

> And step five: prove. After launch, Kiboko measures what actually happened, and tells you whether this project is what moved the number.

Guide:

> Open any completed project to find this panel. The green banner is the verdict in one sentence. <break time="0.4s" /> Below it, the projection sits next to actual sales for the same thirty days, and the per-lever chart shows which levers really moved.

**Scene 8** (back to Pipeline)

Primary:

> For eCommerce brands, and for the agencies and consultants who run their growth. <break time="0.6s" /> Kiboko: know what to do next, and prove it worked.

Guide:

> To get started, connect your data under Settings, Data Connection. <break time="0.4s" /> Then set your objectives and budget, invite your team under Manage Users, and add your first project.

## Video 1: See

Video 1 shows how Kiboko breaks sales into levers that multiply together, and compares each lever against a prior period. It runs about two minutes. The Grow Sales page shows the three-lever form of the equation (Visits x Close Rate x Avg. Order Value = Sales), and six lever cards beneath it. The narration explains how the two forms relate, because the six-lever equation never appears on screen as one line.

### Browser prompt

```text
You are driving Kiboko at http://localhost:8082 for a screen recording.

Rules:
- Move slowly and deliberately. One action at a time.
- After each scene, hold completely still for the stated time (use a wait action; no scrolling or clicking during a hold).
- Wait for every chart to finish rendering before a hold starts.
- Never click Save, Submit, Approve, Delete or Log Out. Never drag Kanban cards. Never open Settings pages, /admin, or any file.
- If a page doesn't match these instructions, stop and tell me instead of improvising.
- Before scene 1: confirm the top bar shows Company = Home Products Company and Business Unit = Lighting. If not, set them, click Apply, and wait for the page to reload.

Scene 1: Go to http://localhost:8082/app/analytics/grow-sales/. Make sure the Period dropdown reads "This Month MTD" and the Comparison period reads "Last Month" (change them if needed and wait for the reload). Scroll to the top so the GROW / SALES hero card and its equation are visible. Hold 13 seconds.
Scene 2: Scroll down slowly until "The Three Levers" panel (ATTRACT, ENGAGE, EXPAND cards) fills the screen. Hold 13 seconds.
Scene 3: Scroll down until the six lever cards are visible: VISITORS, VISITS PER VISITOR, CART CREATION, CART COMPLETION, UNITS PER ORDER, AVG UNIT PRICE. Hold 8 seconds. Then hover the mouse over the card glowing green and hold 5 seconds, then over the card glowing red and hold 5 seconds.
Scene 4: Scroll back to the top. Open the Comparison period dropdown and select "Same Month prior year". Wait for the page to reload and the cards to render. Hold 11 seconds.
Scene 5: In the sidebar, expand Analytics and click Performance Storyboard. Hold 4 seconds on the Brief view. Then click the "Detail" button at the top right of the table (next to "Brief"). The expanded rows open under each lever, for example "New Visitor Visits" and "Returning Visitor Visits" under ATTRACT. Hold 8 seconds. Then scroll down slowly through the ATTRACT, ENGAGE and EXPAND sections, about one section every 4 seconds, and stop on the large "GROW / Total Sales" row at the bottom. Hold 10 seconds.
Scene 6: In the sidebar under Analytics, click Engage Customers. Scroll down to the "Device Close Rate Changeplot". Hold 6 seconds. Hover over one dot in the "Change in Close Rate" chart so the tooltip and the readout below the chart fill in. Hold 9 seconds.
Then tell me "Recording complete".
```

### Narration

**Scene 1** (Grow Sales hero card)

> Kiboko starts with one equation. <break time="0.5s" /> Sales equals visits, times close rate, times average order value. Every number on this page is part of that equation, so the math ties out to the penny.

**Scene 2** (The Three Levers)

> Those three levers map to three jobs. Attract more traffic. Engage shoppers so more of them buy. And expand what each order is worth. Each card tells you, in one sentence, how that lever moved.

**Scene 3** (six lever cards)

> Go one level deeper and there are six levers: visitors, visits per visitor, cart creation, cart completion, units per order, and average unit price. Multiply them together and you get sales. <break time="0.6s" /> The biggest gain glows green. <break time="1.5s" /> The biggest drop glows red.

**Scene 4** (comparison switched to prior year)

> Every comparison works two ways: against the prior period, or against the same period last year. One click separates a seasonal dip from a real problem.

**Scene 5** (Performance Storyboard)

> The Performance Storyboard reads the same levers top to bottom, as a story. <break time="1.0s" /> Switch to Detail, and every supporting metric opens up under its lever: new visitors, returning visitors, cart and checkout steps. <break time="1.0s" /> Attract. Engage. Expand. <break time="1.5s" /> And at the bottom, total sales, with a plain-language sentence on what drove the change.

**Scene 6** (Device Close Rate Changeplot)

> Changeplots show which segments, such as devices or channels, moved each rate. <break time="0.5s" /> Hover any point to see the detail. <break time="0.8s" /> Now everyone is looking at the same numbers, and the argument can move on to what to do about them.

## Video 2: Propose

Video 2 fills in the Project Intake Form, lets the Kiboko Effect estimate the project's value, then pushes the target too far so viewers see the automatic discount. It runs about three minutes. Claude stops before clicking Submit, so nothing is saved. The project moves Units per Order for Lighting, whose baseline is about 1.83 in the seeded data:

| Target | Change | Size of Impact band | What the form shows |
| --- | --- | --- | --- |
| 1.87 | about +2% | Modest | "Within recent range — no discount." Expected = gross x 1.00 |
| 1.98 | about +8% | Strong | "Impact auto-discounted to 52%." Expected = gross x 0.52 |
| 2.11 | about +15% | Extreme | "Impact auto-discounted to 15%." Expected = gross x 0.15 |

### Browser prompt

```text
You are driving Kiboko at http://localhost:8082 for a screen recording.

Rules:
- Move slowly and deliberately. One action at a time. Type at a readable pace.
- After each scene, hold completely still for the stated time (use a wait action; no scrolling or clicking during a hold).
- Wait for every chart, badge and gauge to finish loading before a hold starts.
- Never click "Save progress", "Submit for approval", Approve, Delete or Log Out. Never open Settings pages, /admin, or any file.
- If a page doesn't match these instructions, stop and tell me instead of improvising.
- Before scene 1: confirm the top bar shows Company = Home Products Company. If not, set it, click Apply, and wait.

Scene 1: Click the purple "Add Project" button in the sidebar. Scroll to the top so the "Project Intake Form" header, the "Project details" panel and the locked "Impact estimator" panel are all visible. Hold 11 seconds.
Scene 2: Fill in Project details, one field at a time:
  - Name: Complete-the-look add-ons in cart
  - User Story: As a shopper buying a light fixture, I want matching bulbs, dimmers and mounting kits suggested in my cart, so I get everything I need in one order.
  - Definition of Done: Cart suggests up to three compatible add-ons for every fixture, on desktop and mobile, with one-click add.
  - Objective: Increase Average Order Value
  - Owner: choose the first available option
  - Business Unit: Lighting
  - Department: choose the first available option
  - Target go-live date: 11/16/2026
After the last field, wait for the Impact estimator to unlock. Hold 6 seconds.
Scene 3: In the Impact estimator, set "Lever it moves" to Units per Order. Wait for the baseline source badge, the "Current level (baseline)" value and the "Annual sales baseline" to fill in. Hold 14 seconds.
Scene 4: Click the Window toggle "90d", wait 3 seconds, then click "365d · 52wk" again. Hold 8 seconds.
Scene 5: Type 1.87 in "Target level" and click outside the field so everything recalculates. (If the baseline is not about 1.83, use baseline x 1.02 instead, rounded to 2 decimals.) Scroll so the "Estimated impact" tiles (% Δ Lever, Gross impact / yr, Expected (risk-adjusted), Realized this yr) and the "Size of Impact" gauge with its caption are visible together. Hold 24 seconds.
Scene 6: Change "Target level" to 1.98 (or baseline x 1.08) and click outside the field. Watch the gauge marker move to Strong, the caption change to "Impact auto-discounted to ...", and Expected (risk-adjusted) drop below Gross impact. Hold 22 seconds.
Scene 7: Change "Target level" to 2.11 (or baseline x 1.15) and click outside the field. The gauge moves to Extreme. Hold 14 seconds. Then set "Target level" back to 1.87 (or baseline x 1.02) and click outside. Hold 4 seconds.
Scene 8: Tick the "Evidence-backed target" checkbox so the Evidence type, Evidenced prior level and Evidence note fields appear. Hold 11 seconds. Untick it.
Scene 9: Scroll to the bottom so the Kiboko Effect footnote and the "Submit for approval" button are visible. Hover over "Submit for approval" without clicking. Hold 10 seconds.
Then tell me "Recording complete". Do not submit the form.
```

### Narration

**Scene 1** (blank intake form)

> Anyone can propose a project. The intake form asks for one thing up front: which lever does this project move?

**Scene 2** (details being typed)

> First, the basics. What it is, who it's for, what done looks like, and which objective it serves. <break time="1.0s" /> Here, complete-the-look add-ons in the cart, aimed at bigger orders.

**Scene 3** (lever chosen, baseline loads)

> Then the Kiboko Effect takes over. Pick the lever, units per order, and Kiboko pulls its current level and the annual sales baseline straight from your store's history. No one types in a guess.

**Scene 4** (window toggle)

> The baseline can look back ninety days, half a year, or a full year, so seasonality doesn't skew it.

**Scene 5** (modest target, value estimate)

> Set a modest target: about two percent more units per order. <break time="0.5s" /> Because sales is the product of the six levers, a two percent lift in one lever is a two percent lift in sales. Kiboko turns that into dollars: gross impact over a year, a risk-adjusted expected value, and how much lands this year after the ramp-up. <break time="0.5s" /> This target sits inside the lever's normal range, so there's no discount.

**Scene 6** (aggressive target, discounted)

> Now say someone gets ambitious, and pushes the target to eight percent. <break time="0.5s" /> The Size of Impact gauge measures that against the lever's own weekly swings. This lever rarely moves that far, so Kiboko automatically cuts the expected value to about half. The gross number stays on screen, so everyone can see the discount.

**Scene 7** (extreme target)

> Push it to fifteen percent, and the gauge hits extreme. The expected value drops to a fraction of the gross. <break time="0.6s" /> Over-promising doesn't buy a higher score, so no one can talk a vanity project up.

**Scene 8** (Evidence-backed target)

> Sometimes a big target is justified. Say a site bug cut a rate, and the fix brings it back. Mark the target as evidence-backed, choose the evidence type, and add a note. The note is required, and it's audited.

**Scene 9** (Submit button)

> Submit, and the project enters the pipeline with a defensible estimate attached, and any discount already applied. Next, it gets scored.

## Video 3: Score

Video 3 shows the anonymous vote, then the single blended score it feeds. It runs about two minutes. Record it logged in as `admin`, who is a voting member of Home Products Company. The screen never splits the blended score into its vote half and algorithm half, so the narration explains the split. Four projects are waiting for `admin`'s vote. The prompt uses "Restore mobile add-to-cart after the theme update", which carries an Evidence-backed target shield. Claude moves the sliders but never clicks Save Score, so no vote is cast and the scene can be re-recorded.

### Browser prompt

```text
You are driving Kiboko at http://localhost:8082 for a screen recording.

Rules:
- Move slowly and deliberately. One action at a time.
- After each scene, hold completely still for the stated time (use a wait action; no scrolling or clicking during a hold).
- Wait for every page to finish loading before a hold starts.
- Never click Save Score, Update Score, Approve, "Approve → On Deck", Delete or Log Out. Never drag Kanban cards. Never open Settings pages, /admin, or any file.
- If a page doesn't match these instructions, stop and tell me instead of improvising.
- Before scene 1: confirm the top bar shows Company = Home Products Company and Business Unit = All Business Units. If not, set them, click Apply, and wait.

Scene 1: In the sidebar under Project Prioritization, click Score Projects. Scroll to the top so the "Score Projects · Business Value Model" header, the "awaiting your score" summary and the weighting legend are visible. Hold 13 seconds.
Scene 2: Scroll to the card "Restore mobile add-to-cart after the theme update", which shows an "Evidence-backed target" shield (if it is missing, use the first card). Make sure the card's Gross impact / yr, Expected (risk-adjusted) and realized-this-year figures and its evidence note are visible. Hold 18 seconds.
Scene 3: On that card, move the five sliders one at a time, pausing about 1 second after each: Customer Value to 8, Business Value to 7, Cost Savings to 3, Operational Cost to 4, Business Risk to 5. Watch "Your weighted score" update. Hold 10 seconds. Do not click Save.
Scene 4: Hover over the "X of Y voted" progress bar on the same card. Hold 10 seconds.
Scene 5: In the sidebar under Project Prioritization, click Executive Approval. Make sure the "Awaiting approval" table with its "Score /100" and "Projected value" columns is visible. Hold 16 seconds.
Scene 6: In the sidebar under Project Control, click Backlog. Hold 11 seconds.
Then tell me "Recording complete".
```

### Narration

**Scene 1** (Score Projects header)

> Every proposed project gets scored by the people who know the business. <break time="0.5s" /> Each one is rated on five weighted criteria: customer value, business value, cost savings, operational cost, and business risk.

**Scene 2** (project card)

> Voters see the estimate before they score: the gross impact, the risk-adjusted value, and what it could deliver this year. Every vote starts from the same numbers. <break time="0.6s" /> This one carries an evidence-backed target, so every voter also sees the shield and the note that justifies it.

**Scene 3** (sliders moving)

> Each voter moves five sliders, and their weighted score updates as they go. <break time="0.5s" /> Votes are anonymous, so the loudest voice in the room doesn't decide.

**Scene 4** (voting progress)

> Kiboko tracks how many people have voted. When the last vote is in, the project moves to scored.

**Scene 5** (Executive Approval, Score /100)

> That vote is only half of the score. <break time="0.5s" /> The other half is algorithmic: the project's estimated value, ranked against the rest of the backlog. Kiboko blends the two into one score out of a hundred. The vote can't override the math, and a target the plausibility check flagged as over-aggressive has already been discounted.

**Scene 6** (Backlog)

> The result is one ranked, defensible list. Executives approve from the top, and anyone can see why a project ranks where it does.

## Video 4: Execute

Video 4 follows approved work from sign-off to delivery: the approval steps, the Kanban board, the Work In Progress gantt, and the forward-looking pipeline. It runs about two and a half minutes. Claude approves nothing. It makes one change: it drags the "Bundle shades + bulbs at the PDP" card from SCORED to EXECUTIVE APPROVAL. Reset that card after each take (see the pre-flight checklist) so the next take starts the same way.

### Browser prompt

```text
You are driving Kiboko at http://localhost:8082 for a screen recording.

Rules:
- Move slowly and deliberately. One action at a time.
- After each scene, hold completely still for the stated time (use a wait action; no scrolling or clicking during a hold).
- Wait for every chart and gantt to finish rendering before a hold starts.
- Never click Approve, "Review value", Save, Complete, "Approve → On Deck", Delete or Log Out. The only Kanban card you may drag is "Bundle shades + bulbs at the PDP", and only in scene 3. Never open Settings pages, /admin, or any file.
- If a page doesn't match these instructions, stop and tell me instead of improvising.
- Before scene 1: confirm the top bar shows Company = Home Products Company and Business Unit = All Business Units. If not, set them, click Apply, and wait.

Scene 1: In the sidebar under Project Prioritization, click Approve Projects. Scroll to the top. Hold 6 seconds. Then scroll down slowly through "1. Pending Business Unit Leader Approval", "2. Value Sign-off · Analyst" and "3. Effort & Capability · Lead Developer", pausing about 3 seconds on each. Hold 4 seconds at the end.
Scene 2: In the sidebar, click Executive Approval. Hover over the first "Approve → On Deck" button without clicking. Hold 10 seconds.
Scene 3: In the sidebar under Project Control, click Kanban. Scroll to the top so the Projected Value tiles and all six lanes (BLOCKED, READY TO SCORE, SCORED, EXECUTIVE APPROVAL, ON DECK, WIP) are visible. Hold 10 seconds. Find the "Bundle shades + bulbs at the PDP" card in the SCORED lane and hover over it. Hold 3 seconds. Then press the mouse on that card, drag it slowly into the EXECUTIVE APPROVAL lane, and release it there. Wait for the Projected Value tiles to update. If a red toast message appears instead, stop and tell me what it says. Hold 9 seconds.
Scene 4: In the sidebar under Project Control, click Work In Progress. Click "This Quarter". Wait for the gantt to render. Hold 8 seconds. Hover over the label of a row that shows a link (dependency) icon so its tooltip appears. Hold 10 seconds.
Scene 5: Click "Next Quarter". Wait for the gantt to render with its "On Deck" tags. Hold 12 seconds.
Scene 6: Go to http://localhost:8082/app/ (Project Pipeline Value). Under "Look ahead", click "Next Quarter". Wait for the tiles and the Revenue chart to update. Hold 8 seconds. Then scroll down slowly to the "Projects Summary" table. Hold 8 seconds.
Then tell me "Recording complete".
```

### Narration

**Scene 1** (Approve Projects)

> Before a project can be scored, the right people sign off. The business unit leader approves it. An analyst signs off on the value. And a lead developer sizes the effort and confirms the team can build it.

**Scene 2** (Executive Approval)

> After scoring, executives see the ranked list and approve the work they want. Approved projects move to On Deck.

**Scene 3** (Kanban)

> The Kanban board shows every project by stage, with the projected value of each lane at the top. <break time="0.5s" /> The bundle project is scored, so a business unit lead drags it to Executive Approval, and the lane totals update. <break time="0.5s" /> Every move follows your rules: a project must be scored before it advances, and only an executive can put it On Deck.

**Scene 4** (Work In Progress gantt)

> Work In Progress lays the active work out on a gantt chart, with one lane per team. The red line is today. <break time="0.5s" /> Hover any task to see its progress, its team, and what it depends on.

**Scene 5** (Next Quarter, On Deck tags)

> Look ahead to next quarter, and approved work that hasn't started yet joins the chart, tagged On Deck. You can see what's coming before it lands.

**Scene 6** (Project Pipeline Value, look ahead)

> For executives, the Project Pipeline Value view asks the bigger question. Looking ahead a month, a quarter, or a year, is the approved pipeline building momentum toward the budget, or falling behind it?

## Video 5: Prove

Video 5 opens a launched project and shows Kiboko's verdict on whether that project moved sales. It runs about two minutes. It uses project 19, "Lighting Store nav & search relaunch", which moves the Visitors lever. With the current seed, its banner reads "Sales rose $145,030 in the 30 days after launch, vs a projected gain of $109,096. This project drove the gain — it worked." The Visitors lever accounts for 57% of the change. If you reseed later, check the banner still says "it worked" before recording, since the narration relies on it.

### Browser prompt

```text
You are driving Kiboko at http://localhost:8082 for a screen recording.

Rules:
- Move slowly and deliberately. One action at a time.
- After each scene, hold completely still for the stated time (use a wait action; no scrolling or clicking during a hold).
- Wait for every chart to finish rendering before a hold starts.
- Never click Archive, Delete, Approve, Save or Log Out. Never open Settings pages, /admin, or any file.
- If a page doesn't match these instructions, stop and tell me instead of improvising.
- Before scene 1: confirm the top bar shows Company = Home Products Company and Business Unit = All Business Units. If not, set them, click Apply, and wait.

Scene 1: In the sidebar under Project Review, click Completed Projects. Set "Go-live from" to 02/01/2026 and "Go-live to" to 05/31/2026, then click Apply. Wait for the list to load. Hold 10 seconds.
Scene 2: On the row for "Lighting Store nav & search relaunch", click "Analyze Impact". Wait for the page to load, then scroll so the "Realized Performance" panel title and its coloured verdict banner are at the top of the screen. Hold 15 seconds.
Scene 3: Scroll down slightly so the estimate-vs-actual table (Projected total sales (gross), Projected total sales (risk-adjusted), Actual total sales) is fully visible. Hold 12 seconds.
Scene 4: Scroll to the "How we know — the numbers" tiles. Hold 12 seconds.
Scene 5: Scroll to the "Per-lever contribution" bar chart. Hold 15 seconds.
Scene 6: Scroll to the "Daily sales · 7-day avg" chart. Hover over a point after the launch date so the tooltip appears. Hold 12 seconds.
Scene 7: Scroll back up to the verdict banner. Hold 10 seconds.
Then tell me "Recording complete".
```

### Narration

**Scene 1** (Completed Projects)

> Shipping a project isn't the finish line. The real question is whether it worked. <break time="0.5s" /> Every completed project in Kiboko can be measured against its own estimate.

**Scene 2** (Realized Performance verdict)

> Here's the Lighting Store navigation and search relaunch. <break time="0.5s" /> Kiboko compares the weeks after launch, once the ramp-up is over, with the period before launch. It then writes the verdict in plain language: did sales move, and was it this project that moved them? <break time="0.8s" /> Here the answer is yes. Sales rose more than projected, and the visitors lever this project targeted drove most of the gain.

**Scene 3** (estimate vs actual)

> The estimate made at intake sits next to what really happened: gross projection, risk-adjusted projection, and actual sales.

**Scene 4** (How we know tiles)

> Then the evidence. How much sales changed, how much of that change came from this project's lever, and how far the lever actually moved compared with the plan: about eight percent, against a planned ten.

**Scene 5** (Per-lever contribution)

> This chart breaks the actual sales change into every lever. It uses a standard decomposition method, so the pieces add up exactly to the total. <break time="0.5s" /> If sales rose because of something else, like price or a seasonal swing, you'll see it here instead of the project taking credit.

**Scene 6** (Daily sales, 7-day avg)

> And the daily view, with the average before and after launch drawn as dashed lines.

**Scene 7** (back to verdict)

> Estimate before, measure after, on the same lever model. <break time="0.6s" /> That closes the loop, and the next round of prioritization starts with evidence of what actually works.

## Pre-flight checklist and troubleshooting

Run every prompt once without recording. Any mismatch then shows up in a test run, not halfway through a take. The project IDs here were checked against the local MySQL database on Oct 23, 2026.

### Before recording

- [ ] Start MySQL, then run `python manage.py runserver 8082` from the repo with the virtualenv active.
- [ ] Log in at http://localhost:8082/users/login/ as `admin` (superuser and Home Products Company voter). Superusers see every menu, including Project Control and Project Review.
- [ ] Set the top bar to Company = **Home Products Company** and click Apply. Home Products Company runs on seeded daily actuals, so no GA4 or BigQuery connection is needed.
- [ ] Open http://localhost:8082/project/19/ and confirm it is "Lighting Store nav & search relaunch" with a Realized Performance panel. If the ID differs in MySQL, update the URLs in Video 0 scene 7 and Video 5.
- [ ] Check that Score Projects has at least one card awaiting your vote, that Executive Approval has at least one row, and that the Kanban ON DECK lane has a card.
- [ ] Open Backlog and confirm it is sorted by score. If it isn't, end Video 3 on scene 5 and cut the scene 6 narration.
- [ ] Close every editor, terminal and Finder window that shows `local_settings.py`, `client_secret_*.json` or the `mysql_creds` files, so none of them appear in a recording.
- [ ] Turn on Focus mode and hide the Dock.
- [ ] After each Video 4 take, put the Bundle card back in SCORED and remove the comment the move logged:

```bash
python manage.py shell -c "from strategy.models import Project, ProjectComment; p = Project.objects.get(name='Bundle shades + bulbs at the PDP'); p.status = 'Scored'; p.save(); ProjectComment.objects.filter(project=p, text__contains='moved this from').delete()"
```

- [ ] To refresh the demo data (for example, to move the latest day forward before a later recording session), run `python manage.py seed_belami_demo --to <yesterday's date, YYYY-MM-DD>`. The seeded actuals currently run through 2026-10-22.

### Troubleshooting

| What you see | Cause | Fix |
| --- | --- | --- |
| Pages load slowly or fail | Company defaulted to Autocado, which makes live BigQuery calls | Set Company = Home Products Company and click Apply |
| "Live data available — Sign in with Google" banner instead of charts | Demo Account or VOLT Lighting is selected; both have GA4 properties | Switch to Home Products Company |
| Dashboards look empty or stale for This Month MTD | The seeded actuals stop at the last seeded day (currently 2026-10-22) | Reseed with `python manage.py seed_belami_demo --to <yesterday>` |
| Changeplot dots bunch into a line | Daily actuals apply a fixed device and channel mix, so all segments move by the same percentage | Expected with seeded data. Hover any dot, or drop Video 1 scene 6 |
| Impact estimator stays locked | A Project details field is blank | Fill every field, including Owner, Department and go-live date |
| Size of Impact gauge is greyed out | The selected business unit has less than 3 weeks of history | Use Business Unit = Lighting |
| "Not enough post-launch data yet", or a verdict other than "it worked", on project 19 | The data was reseeded with different dates, or the go-live moved | Reseed with `python manage.py seed_belami_demo --to <yesterday>`, which re-applies the project's lift. The other completed projects (18, 20, 21, 22) intentionally show mixed results, so they don't fit the Video 5 narration |
| Product Category AOV Changeplot shows "Premium Tier Required" | Home Products Company has no BigQuery connection | Expected. Video 1 uses the Device changeplot on Engage Customers |
| The Bundle card won't drop into EXECUTIVE APPROVAL, or a toast says "Project must be scored first" | The card was already moved in an earlier take, or its score was cleared | Run the Bundle reset command above, reload the Kanban, and retake |
| Claude clicks the wrong thing mid-take | The page layout differs from the prompt | Stop the recording, then rerun from that scene: paste the rules block plus only the remaining scenes |
