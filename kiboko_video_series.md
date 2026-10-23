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

The intro runs about 90 seconds. It stops once on each loop step and does not explain any of them in depth. Start on any Kiboko page with Company = Home Products Company applied.

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

Scene 1: Go to http://localhost:8082/app/ (Project Pipeline Value). Scroll to the very top. Hold 14 seconds.
Scene 2: Scroll down slowly until the "Revenue" chart and its summary (Actual, Trending Forecast, Prorated Projected Value, Budget, Delta to Budget) fill the screen. Hold 12 seconds.
Scene 3: In the sidebar, expand Analytics and click Performance Storyboard. Hold 10 seconds.
Scene 4: Click the purple "Add Project" button in the sidebar. Hold 9 seconds.
Scene 5: In the sidebar under Project Prioritization, click Score Projects. Hold 10 seconds.
Scene 6: In the sidebar under Project Control, click Kanban. Hold 10 seconds.
Scene 7: Go to http://localhost:8082/project/19/#realized and scroll so the "Realized Performance" panel and its verdict banner are on screen. Hold 11 seconds.
Scene 8: Go back to http://localhost:8082/app/ and scroll to the top. Hold 14 seconds.
Then tell me "Recording complete".
```

### Narration

**Scene 1** (Project Pipeline Value)

> Every eCommerce team has more ideas than it has time to build. <break time="0.6s" /> So which one goes next? And once it ships, did it actually work? <break time="0.8s" /> Kiboko answers both questions.

**Scene 2** (Revenue chart)

> Kiboko is a RevOps platform for eCommerce. It turns your store analytics into a prioritized, defensible project pipeline, and then tracks whether the work moved revenue.

**Scene 3** (Performance Storyboard)

> It isn't another analytics dashboard, and it isn't a project tool. It sits between the two, as one connected loop. <break time="0.5s" /> Step one: see.

**Scene 4** (Add Project)

> Step two: propose. Anyone can submit a project, and Kiboko estimates the revenue it could add.

**Scene 5** (Score Projects)

> Step three: score. A team vote and the math combine into one score, so the strongest ideas rise to the top.

**Scene 6** (Kanban)

> Step four: execute. Approved work moves from intake to approval to delivery, in one place.

**Scene 7** (Realized Performance)

> And step five: prove. After launch, Kiboko measures what actually happened, and tells you whether this project is what moved the number.

**Scene 8** (back to Pipeline)

> For eCommerce brands, and for the agencies and consultants who run their growth. <break time="0.6s" /> Kiboko: know what to do next, and prove it worked.

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
Scene 5: In the sidebar, expand Analytics and click Performance Storyboard. Click the "Detail" toggle so all rows show. Hold 6 seconds. Then scroll down slowly through the ATTRACT, ENGAGE and EXPAND sections, about one section every 4 seconds, and stop on the large "GROW / Total Sales" row at the bottom. Hold 10 seconds.
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

> The Performance Storyboard reads the same levers top to bottom, as a story. <break time="1.0s" /> Attract. Engage. Expand. <break time="1.5s" /> And at the bottom, total sales, with a plain-language sentence on what drove the change.

**Scene 6** (Device Close Rate Changeplot)

> Changeplots show which segments, such as devices or channels, moved each rate. <break time="0.5s" /> Hover any point to see the detail. <break time="0.8s" /> Now everyone is looking at the same numbers, and the argument can move on to what to do about them.

## Video 2: Propose

Video 2 fills in the Project Intake Form and lets the Kiboko Effect estimate the project's value. It runs about two and a half minutes. Claude stops before clicking Submit, so nothing is saved. The impact estimator stays locked until the project details are complete, and the Objective field controls which levers appear in the list.

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
  - Name: Free-shipping threshold nudge in cart
  - User Story: As a shopper close to the free-shipping threshold, I want to see how much more to add, so I can add one more item and save on shipping.
  - Definition of Done: Cart shows a progress bar to the free-shipping threshold on desktop and mobile, with a recommended add-on item.
  - Objective: Increase Average Order Value
  - Owner: choose the first available option
  - Business Unit: Lighting
  - Department: choose the first available option
  - Target go-live date: 12/01/2026
After the last field, wait for the Impact estimator to unlock. Hold 6 seconds.
Scene 3: In the Impact estimator, set "Lever it moves" to Units per Order. Wait for the baseline source badge and the "Current level (baseline)" value to load. Hold 13 seconds.
Scene 4: Click the Window toggle "90d", wait 3 seconds, then click "365d · 52wk" again. Hold 8 seconds.
Scene 5: Read the Current level (baseline) value. Enter a Target level about 5% higher (baseline x 1.05, rounded to 2 decimals). Click outside the field so the tiles recalculate. Scroll so the "Estimated impact" tiles (% Δ Lever, Gross impact / yr, Expected (risk-adjusted), Realized this yr) are visible. Hold 16 seconds.
Scene 6: Scroll so the "Size of Impact" gauge is visible. Hold 5 seconds. Change the Target level to about 40% above baseline (baseline x 1.40), click outside the field, and watch the gauge move. Hold 10 seconds. Then set the Target level back to the 5% value and click outside. Hold 4 seconds.
Scene 7: Tick the "Evidence-backed target" checkbox so the Evidence type, Evidenced prior level and Evidence note fields appear. Hold 11 seconds. Untick it.
Scene 8: Scroll to the bottom so the Kiboko Effect footnote and the "Submit for approval" button are visible. Hover over "Submit for approval" without clicking. Hold 10 seconds.
Then tell me "Recording complete". Do not submit the form.
```

### Narration

**Scene 1** (blank intake form)

> Anyone can propose a project. The intake form asks for one thing up front: which lever does this project move?

**Scene 2** (details being typed)

> First, the basics. What it is, who it's for, what done looks like, and which objective it serves. <break time="1.0s" /> Here, a free-shipping nudge in the cart, aimed at bigger orders.

**Scene 3** (lever chosen, baseline loads)

> Then the Kiboko Effect takes over. Pick the lever, units per order, and Kiboko pulls its current level straight from your store's history. No one types in a baseline by hand.

**Scene 4** (window toggle)

> The baseline can look back ninety days, half a year, or a full year, so seasonality doesn't skew it.

**Scene 5** (target set, impact tiles)

> Set a target, here five percent higher, and Kiboko works out the value. <break time="0.5s" /> Gross impact over a year. A risk-adjusted expected value. And how much of it lands this year, after the ramp-up. <break time="0.5s" /> This replaces the old step where an analyst typed in a guess.

**Scene 6** (Size of Impact gauge)

> The Size of Impact gauge checks the target against the lever's own history. <break time="1.0s" /> Push it to forty percent and the gauge swings to extreme. Over-aggressive targets get discounted automatically, so no one can talk a vanity project up.

**Scene 7** (Evidence-backed target)

> Sometimes a big target is justified. Say a site bug cut a rate, and the fix brings it back. Mark the target as evidence-backed, choose the evidence type, and add a note. The note is required, and it's audited.

**Scene 8** (Submit button)

> One submit, and the project enters the pipeline with a defensible, data-backed estimate attached. Next, it gets scored.

## Video 3: Score

Video 3 shows the anonymous vote, then the single blended score it feeds. It runs about two minutes. Record it logged in as `admin`, who is a voting member of Home Products Company. The screen never splits the blended score into its vote half and algorithm half, so the narration explains the split. Claude moves the sliders but never clicks Save Score, so no vote is cast.

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
Scene 2: Scroll to the first project card. If any card on the page shows an "Evidence-backed target" shield, scroll to that card instead. Make sure the card's Gross impact / yr, Expected (risk-adjusted) and realized-this-year figures are visible. Hold 13 seconds.
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

> Voters see the estimate before they score: the gross impact, the risk-adjusted value, and what it could deliver this year. Every vote starts from the same numbers.

**Scene 3** (sliders moving)

> Each voter moves five sliders, and their weighted score updates as they go. <break time="0.5s" /> Votes are anonymous, so the loudest voice in the room doesn't decide.

**Scene 4** (voting progress)

> Kiboko tracks how many people have voted. When the last vote is in, the project moves to scored.

**Scene 5** (Executive Approval, Score /100)

> That vote is only half of the score. <break time="0.5s" /> The other half is algorithmic: the project's estimated value, ranked against the rest of the backlog. Kiboko blends the two into one score out of a hundred. The vote can't override the math, and a target the plausibility check flagged as over-aggressive has already been discounted.

**Scene 6** (Backlog)

> The result is one ranked, defensible list. Executives approve from the top, and anyone can see why a project ranks where it does.

## Video 4: Execute

Video 4 follows approved work from sign-off to delivery: the approval steps, the Kanban board, the Work In Progress gantt, and the forward-looking pipeline. It runs about two and a half minutes. Claude only looks and hovers. It approves nothing and drags no cards.

### Browser prompt

```text
You are driving Kiboko at http://localhost:8082 for a screen recording.

Rules:
- Move slowly and deliberately. One action at a time.
- After each scene, hold completely still for the stated time (use a wait action; no scrolling or clicking during a hold).
- Wait for every chart and gantt to finish rendering before a hold starts.
- Never click Approve, "Review value", Save, Complete, "Approve → On Deck", Delete or Log Out. Never drag Kanban cards. Never open Settings pages, /admin, or any file.
- If a page doesn't match these instructions, stop and tell me instead of improvising.
- Before scene 1: confirm the top bar shows Company = Home Products Company and Business Unit = All Business Units. If not, set them, click Apply, and wait.

Scene 1: In the sidebar under Project Prioritization, click Approve Projects. Scroll to the top. Hold 6 seconds. Then scroll down slowly through "1. Pending Business Unit Leader Approval", "2. Value Sign-off · Analyst" and "3. Effort & Capability · Lead Developer", pausing about 3 seconds on each. Hold 4 seconds at the end.
Scene 2: In the sidebar, click Executive Approval. Hover over the first "Approve → On Deck" button without clicking. Hold 10 seconds.
Scene 3: In the sidebar under Project Control, click Kanban. Scroll to the top so the Projected Value tiles and all six lanes (BLOCKED, READY TO SCORE, SCORED, EXECUTIVE APPROVAL, ON DECK, WIP) are visible. Hold 10 seconds. Then hover over the first card in the ON DECK lane. Hold 8 seconds.
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

> The Kanban board shows every project by stage, with the projected value of each lane at the top. <break time="0.5s" /> Moves follow your rules: a project must be scored before it advances, and only an executive can put it On Deck.

**Scene 4** (Work In Progress gantt)

> Work In Progress lays the active work out on a gantt chart, with one lane per team. The red line is today. <break time="0.5s" /> Hover any task to see its progress, its team, and what it depends on.

**Scene 5** (Next Quarter, On Deck tags)

> Look ahead to next quarter, and approved work that hasn't started yet joins the chart, tagged On Deck. You can see what's coming before it lands.

**Scene 6** (Project Pipeline Value, look ahead)

> For executives, the Project Pipeline Value view asks the bigger question. Looking ahead a month, a quarter, or a year, is the approved pipeline building momentum toward the budget, or falling behind it?

## Video 5: Prove

Video 5 opens a launched project and shows Kiboko's verdict on whether that project moved sales. It runs about two minutes. It uses project 19, "Lighting Store nav & search relaunch", which moves the Visitors lever. The verdict text depends on the data, so the narration describes what the banner does without quoting it. If you'd like the voiceover to state the result, read the banner during your test run and add one sentence to scene 2.

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

> Here's the Lighting Store navigation and search relaunch. <break time="0.5s" /> Kiboko compares the weeks after launch, once the ramp-up is over, with the period before launch. It then writes the verdict in plain language: did sales move, and was it this project that moved them?

**Scene 3** (estimate vs actual)

> The estimate made at intake sits next to what really happened: gross projection, risk-adjusted projection, and actual sales.

**Scene 4** (How we know tiles)

> Then the evidence. How much sales changed, how much of that change came from this project's lever, and how far the lever actually moved compared with the plan.

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

### Troubleshooting

| What you see | Cause | Fix |
| --- | --- | --- |
| Pages load slowly or fail | Company defaulted to Autocado, which makes live BigQuery calls | Set Company = Home Products Company and click Apply |
| "Live data available — Sign in with Google" banner instead of charts | Demo Account or VOLT Lighting is selected; both have GA4 properties | Switch to Home Products Company |
| Dashboards look empty for This Month MTD | The seeded actuals end 2026-09-24 | Set Period to Last Month, or reseed with `python manage.py seed_belami_demo` |
| Changeplot dots bunch into a line | Daily actuals apply a fixed device and channel mix, so all segments move by the same percentage | Expected with seeded data. Hover any dot, or drop Video 1 scene 6 |
| Impact estimator stays locked | A Project details field is blank | Fill every field, including Owner, Department and go-live date |
| Size of Impact gauge is greyed out | The selected business unit has less than 3 weeks of history | Use Business Unit = Lighting |
| "Not enough post-launch data yet" on Realized Performance | The measurement window hasn't finished | Use project 18, 20 or 22 instead, and update the name in Video 5 scene 2 |
| Product Category AOV Changeplot shows "Premium Tier Required" | Home Products Company has no BigQuery connection | Expected. Video 1 uses the Device changeplot on Engage Customers |
| Claude clicks the wrong thing mid-take | The page layout differs from the prompt | Stop the recording, then rerun from that scene: paste the rules block plus only the remaining scenes |
