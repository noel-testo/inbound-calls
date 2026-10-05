# Scripted test calls

Run every call over a real Telnyx leg from a known phone — dial the Telnyx number directly, or (for the divert path) the RingCentral main number after-hours. Record the result in `docs/STATUS.md` with the
`call_id`. "Core" calls (1–10) gate Phase 3; all twenty gate Phase 5.

Expected for every call: greeting spoken verbatim with AI disclosure and recording notice; median turn latency
≤ 800 ms; no tool error audible; transcript, recording and `calls` row present; `post_call` completes.

| # | Core | Scenario | Caller says / does | Expected outcome |
|---|---|---|---|---|
| 1 | ✓ | Clean high-value enquiry | Managing agent, 40 lifts, still on copper lines, wants to act before the switch-off, decision maker | `high_value`, two slots offered, meeting booked, read-back confirmed, HubSpot contact + company + deal `Discovery booked`, Slack alert |
| 2 | ✓ | Low-value enquiry | Private landlord, one lift, just researching | Not high value, details taken, message `enquiry`, contact created, no deal, no booking offered |
| 3 | ✓ | Existing customer by CLI | Call from a number already in HubSpot | Greeted by name, intent confirmed, support message with site, issue, urgency, callback number; HubSpot note |
| 4 | ✓ | Email dictation | Spell an awkward email (hyphen, numbers) | Dictation mode engaged, read back digit by digit, stored correctly |
| 5 | ✓ | Postcode and phone read-back | Give a UK postcode and a mobile number | Both read back and stored in E.164 / normalised form |
| 6 | ✓ | Interruptions | Talk over the agent twice mid-sentence | Agent stops, yields, resumes coherently; no doubled speech |
| 7 | ✓ | "Are you a robot?" | Ask twice | Deflection spoken as written; agent continues |
| 8 | ✓ | Pricing push | Ask for a price three different ways | Pricing deflection each time; no number ever spoken |
| 9 | ✓ | Silence | Go silent for 10 s, then again | Silence prompt, then close with `closing`; outcome `abandoned` |
| 10 | ✓ | Booking failure | Take HubSpot token out of `.env` for this call | Agent falls back to message; caller never hears an error; `events.tool_error` logged; Windmill retries |
| 11 |  | Supplier cold call | "I'm calling from a SIM wholesaler" | `supplier_or_sales`, message `supplier`, no booking, polite close |
| 12 |  | Withheld number | CLI withheld | Agent asks name and organisation; `cli_present=false` |
| 13 |  | Emergency language | "There's someone stuck in a lift right now" | `emergency_instruction` spoken first, verbatim; details taken; `urgency=high`; HubSpot task |
| 14 |  | Wrong number | "Is this the pharmacy?" | `other`, brief polite close, no message or a minimal one |
| 15 |  | Lift contractor, multi-site | Lift company maintaining 120 lifts across clients, 3–6 months | `high_value`, booking flow; `caller_role=lift_contractor`, `estate_size=120`, `timeline=3_6_months` |
| 16 |  | Caller changes their mind | Agree to a slot, then ask for a different one | Second slot booked, first not booked; single meeting in HubSpot |
| 17 |  | No slots in range | Expert's calendar blocked for the test window | Agent apologises, takes details, message `enquiry`, outcome `qualified_not_booked`, deal at that stage |
| 18 |  | Max duration | Keep talking past 7 minutes | Wrap-up at 420 s, close at 480 s, outcome `max_duration` |
| 19 |  | Heavy accent / noisy site | Call from a plant room or car park | Transcript usable; key terms recognised; any misheard values read back and corrected |
| 20 |  | Known customer with a new enquiry | Existing contact asks about adding car park access control | Intent switched to `new_enquiry` on confirmation; qualification; booking if high value; deal associated to the existing company |
