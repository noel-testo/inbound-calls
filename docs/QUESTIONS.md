# Questions for Noel

Non-blocking questions go under **Open** with the default Claude Code will use until answered. Blocking
questions are raised in the session immediately and recorded here afterwards.

## Open

- **Expert:** who takes discovery calls, their HubSpot user, and their meeting link slug. *Default:* none; blocking for Phase 1.
- **HubSpot pipeline:** use an existing deal pipeline and stages, or create `Inbound`? *Default:* create `Inbound`.
- **Business hours** for `config/greeting.yaml` and for "after hours". *Default:* Mon–Fri 09:00–17:30.
- **Greeting, closing, emergency instruction** wording. *Default:* the TODO placeholders stay until approved; blocking for Phase 5.
- **Voice:** Cartesia or ElevenLabs, and which British English voice. *Default:* Cartesia, first suitable British voice, for Phase 3 testing only.
- **LLM endpoint for the MVP:** which hosted model behind `LLM_BASE_URL`. *Default:* whichever is already paid for; swapped later.
- **Scoring:** confirm or change weights and the threshold (50) in `config/scoring.yaml`. *Default:* as shipped.
- **Retention:** recordings 90 days; transcripts kept indefinitely? *Default:* 90 / indefinite.
- **Host:** existing server or a new UK VPS; who holds root. *Default:* new VPS, 4 vCPU / 8 GB.
- **RingCentral:** admin access to add the existing-phone device and edit call-handling rules; the receptionist extension number. *Default:* none; blocking for Phase 2.
- **n8n:** export of the current RingCentral missed-call workflow JSON. *Default:* none; blocking for Phase 4.
- **Terms list:** product names, staff names, major client and site names for `config/terms.yaml`. *Default:* placeholders.
- **Apollo → HubSpot sync:** confirm it is one-way (enrichment only) so the agent is the only thing creating deals. *Default:* assume yes.

## Answered

(none yet)
