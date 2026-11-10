# Scripted test calls

Run every call over a real Telnyx leg from a known phone — dial the Telnyx number directly, or (for the divert path) the RingCentral main number after-hours. Record the result in `docs/STATUS.md` with the
`call_id`. "Core" calls (1–10) gate Phase 3; all thirty gate Phase 5.

Expected for every call: greeting spoken verbatim with AI disclosure and the approved call-logging notice; median
turn latency ≤ 800 ms; no tool error audible; a Notion "Cody leads" row and a
"Call transcripts" row present (written by n8n). Apollo records and a Slack alert appear **only** for
qualified callers, plus one quiet Slack line when a cold call is declined on Noel's direct line
(call 29). No caller is ever added to an Apollo sequence.

| # | Core | Scenario | Caller says / does | Expected outcome |
|---|---|---|---|---|
| 1 | ✓ | Clean high-value enquiry | Managing agent, 40 lifts, still on copper lines, wants to act before the switch-off, decision maker | `high_value`, offered as a 15-minute call with Noel Sesto, our Technical Director, two slots offered, meeting booked, read-back names Noel Sesto and confirms date, time, name and email, outcome `discovery_booked`; Apollo account + linked contact + call record (`call_identifier` = conversation id) + follow-up task (+ deal if `APOLLO_CREATE_DEALS=true`); Slack alert |
| 2 | ✓ | Low-value enquiry | Private landlord, one lift, just researching | Not high value, details taken, message `enquiry`, Notion lead row `Qualified` unticked, nothing in Apollo, no Slack alert, no booking offered |
| 3 | ✓ | Existing customer by CLI | Call from a number already in the Notion "Cody leads" Phone field (a customer) | Greeted by name, intent confirmed, support message with site, issue, urgency, callback number; outcome `support_message` |
| 4 | ✓ | Email dictation | Spell an awkward email (hyphen, numbers) | Dictation mode engaged, read back digit by digit, stored correctly |
| 5 | ✓ | Postcode and phone read-back | Give a UK postcode and a mobile number | Both read back and stored in E.164 / normalised form |
| 6 | ✓ | Interruptions | Talk over the agent twice mid-sentence | Agent stops, yields, resumes coherently; no doubled speech |
| 7 | ✓ | "Are you a robot?" | Ask twice | Deflection spoken as written; agent continues |
| 8 | ✓ | Pricing push | Ask for a price three different ways | Pricing deflection each time; no number ever spoken |
| 9 | ✓ | Silence | Go silent for 10 s, then again | Silence prompt, then close with `closing`; outcome `abandoned` |
| 10 | ✓ | Booking failure | Take `CALCOM_API_KEY` out of `.env` for this call | Agent falls back to message; caller never hears an error; a `tool_error` log line with the `call_id` |
| 11 |  | Supplier cold call | "I'm calling from a SIM wholesaler" | `supplier_or_sales`, message `supplier`, no booking, polite close |
| 12 |  | Withheld number | CLI withheld | Agent asks name and organisation; `caller_known=false` |
| 13 |  | Emergency language | "There's someone stuck in a lift right now" | No emergency script is spoken. On Noel direct the call is screened and transferred, not declined as a cold call. On any other line it is handled as a normal call for that line |
| 14 |  | Wrong number | "Is this the pharmacy?" | `other`, brief polite close, no message or a minimal one |
| 15 |  | Lift contractor, multi-site | Lift company maintaining 120 lifts across clients, 3–6 months | `high_value`, booking flow; `caller_role=lift_contractor`, `estate_size=120`, `timeline=3_6_months` |
| 16 |  | Caller changes their mind | Agree to a slot, then ask for a different one | Second slot booked, first not booked; a single Cal.com booking |
| 17 |  | No slots in range | Noel Sesto's calendar blocked for the test window | Agent apologises, takes details, message `enquiry`, outcome `qualified_not_booked`; Apollo contact + task; Slack alert |
| 18 |  | Max duration | Keep talking past 7 minutes | Wrap-up at 420 s, close at 480 s, outcome `max_duration` |
| 19 |  | Heavy accent / noisy site | Call from a plant room or car park | Transcript usable; key terms recognised; any misheard values read back and corrected |
| 20 |  | Known customer with a new enquiry | Existing contact asks about adding car park access control | Intent switched to `new_enquiry` on confirmation; qualification; booking if high value; the caller's existing Apollo contact and account are reused (no duplicates) |
| 21 |  | Re-delivered webhook | Replay the same post-call webhook (ElevenLabs retry, or re-run the n8n execution) | Nothing duplicated in Notion, Apollo or Slack |
| 22 |  | Noel direct, answered | Dial `+442045200783` from the RingCentral DDI `020 8158 4403` (CLI `02081584403`). Give name, company, reason and a call-back number | Noel direct greeting; no enquiry questions; call-back number read back; `transfer_to_number` puts the call through to Noel's mobile; Notion rows have Line `noel-direct`, outcome `transferred`, Phone empty and Callback number set; Slack names the line |
| 23 |  | Noel direct, no answer | As 22, Noel's mobile rejects the call | Cody says Noel can't take the call, takes a message with the call-back number; outcome `message_taken`, Line `noel-direct`; the caller never hears a tool error |
| 24 |  | Noel direct, voicemail | As 22, Noel's mobile goes to voicemail | Record what the caller hears (QUESTIONS: voicemail) |
| 25 |  | Parking line | Dial `+442045208242` from a known mobile | Parking greeting; the real caller ID is used (known caller greeted by name); Notion Line `parking`; Slack names the parking line |
| 26 |  | Parking booking | As 25, a high-value enquiry that books | Cal.com booking titled "[Parking] Discovery call with Noel Sesto, Technical Director – <organisation>" with `metadata.line = parking` on event 7747197 |
| 27 |  | Generic 020 | Dial `+442045200783` from any other number | Unchanged greeting and behaviour; Line `general`; no transfer offered |
| 28 |  | RC sales, accounts, support | Dial each DDI: sales 020 3478 0784, accounts 020 3478 0785, support 020 3478 0786 (each forwards to `+442045200783` with that DDI as the CLI) | That line's greeting and Line tag; a call-back number is always asked; no caller lookup; no transfer |
| 29 |  | Noel direct, cold sales call | As 22. The caller is clearly selling (SEO, lead generation, an energy contract, a marketing list) | Cody says "Noel doesn't take unsolicited sales calls. Thank you for calling." and ends the call. No transfer, no message, no call-back number asked. Notion Line `noel-direct`, outcome `cold_call_declined`, Review "Not a lead". Slack is one line and does not ask for a call-back |
| 30 |  | JustPark, any line | Call any ControlFreq number and say you are from JustPark, or from JustPark driver support | Cody skips the enquiry questions and the cold-call check, says "Please hold while I try to put you through." and transfers to Noel's mobile. If the transfer fails: urgency high, and exactly "We'll call you back as soon as practically possible." Notion Partner `justpark` and the Slack line says JustPark |
