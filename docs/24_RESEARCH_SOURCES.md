# 24 — Research sources and evidence limits

All sources below were reviewed or retrieval-attempted on **19 September 2026**. This is a dated research snapshot; official SDK, model, pricing and legal pages can change. Links point to source pages, not search results. No vendor was contacted and no product trial was performed.

**Evidence classes:** EVENT = official published event information; PUBLIC = regulator/government/ombudsman evidence; DOC = official technical documentation; VENDOR = company marketing claim, not independently proven; LIMITED = inaccessible or insufficient detail. Architectural decisions elsewhere are our designs/inferences, not claims made by these sources.

## Event and business

| ID | Source | Supports / limits |
|---|---|---|
| E01 | [Official Luma event](https://luma.com/ldn-hack) | EVENT: schedule, opt-in/live demos, hosts/partners and unspecified credits; detailed rules and full date not exposed in retrieved text |
| B01 | [RSH Tenant Satisfaction Measures 2024/25 headline report](https://www.gov.uk/government/statistics/tenant-satisfaction-measures-202425/tenant-satisfaction-measures-202425-headline-report) | PUBLIC: published 4 Nov 2025; English large social landlords; repair targets/satisfaction; not private-lettings ROI |
| B02 | [Housing Ombudsman repairs spotlight](https://www.housing-ombudsman.org.uk/spotlight-report-on-repairs-complaints-final/) | PUBLIC: March 2019, case F roof/scaffolding sequence; selected historical complaint |
| B03 | [Housing Ombudsman August 2025 learning](https://www.housing-ombudsman.org.uk/reports/learning-from-severe-maladministration-reports/august-2025/) | PUBLIC: dependencies, communication and contractor oversight; severe cases are not prevalence data |
| B04 | [Private renting: repairs](https://www.gov.uk/private-renting/repairs) | PUBLIC: landlord/tenant repair responsibilities |
| B05 | [Landlord safety responsibilities](https://www.gov.uk/private-renting/your-landlords-safety-responsibilities) | PUBLIC: safety obligations; not application-specific legal clearance |
| B06 | [Awaab's Law guidance](https://www.gov.uk/government/publications/awaabs-law-guidance-for-social-landlords/awaabs-law-guidance-for-social-landlords-timeframes-for-repairs-in-the-social-rented-sector) | PUBLIC: current English social-housing guidance, distinct work/timeframe concepts and roof/scaffolding example; scope must be checked |
| B07 | [NHS carbon monoxide guidance](https://www.nhs.uk/conditions/carbon-monoxide-poisoning/) | PUBLIC: emergency routing/helpline; not a diagnostic protocol for the app |
| B08 | [ICO storage limitation](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/a-guide-to-the-data-protection-principles/storage-limitation/) | PUBLIC: justified retention, no universal fixed period; page notes guidance review after legislation changes |

## Competitors — all VENDOR unless marked otherwise

| ID | Sources | Use |
|---|---|---|
| C01 | [Fixflo](https://www.fixflo.com/), [Aidenn](https://www.fixflo.com/solutions/aidenn-ai-repairs-maintenance), [workflow](https://www.fixflo.com/features/workflow-management) | UK reporting, diagnostic AI and workflow claims |
| C02 | [Plentific product navigation](https://www.plentific.com/careers/), [AI](https://www.plentific.com/ai-powered-property-operations/), [work orders](https://www.plentific.com/work-order-management/) | LIMITED: navigation accessible; detailed AI/work-order bodies largely unavailable |
| C03 | [Property Meld MAX](https://propertymeld.com/max-intelligence/), [pricing/features](https://propertymeld.com/pricing/), [Mezo acquisition](https://propertymeld.com/property-meld-mezo/) | Coordination/voice claims and current ownership; no adoption of advertised accuracy figures |
| C04 | [Arthur](https://www.arthuronline.co.uk/), [workflow](https://www.arthuronline.co.uk/features/workflow-management) | Tenant/contractor workflow automation |
| C05 | [MRI housing](https://www.mrisoftware.com/uk/solutions/social-housing/), [asset/repairs](https://www.mrisoftware.com/uk/solutions/social-housing/asset-and-repairs/) | Suite-level overlap; module-specific capabilities not independently tested |
| C06 | [Re-Leased operations](https://www.re-leased.com/product/property-operations-maintenance), [platform/Credia](https://www.re-leased.com/) | Commercial-property maintenance and assisted actions |
| C07 | [Buildium maintenance](https://www.buildium.com/features/property-management-maintenance-software/) | Lumina maintenance agent, projects/contact-centre claims |
| C08 | [AppFolio maintenance](https://www.appfolio.com/property-manager/maintenance), [AI](https://www.appfolio.com/ai) | Explicit autonomous maintenance coordinator and Lula dispatch integration claims |
| C09 | [Propertyware](https://www.propertyware.com/), [work-order tracking](https://www.propertyware.com/work-order-tracking-app/) | Work-order/contact-centre/API overlap |
| C10 | [askporter](https://www.askporter.com/), [repair journey](https://www.askporter.com/housing/repair-journey) | UK end-to-end repair coordination/rescheduling claims |
| C11 | [EliseAI maintenance](https://eliseai.com/maintenance) | Voice, intake, routing and scheduling claims |
| C12 | [Latchel](https://latchel.com/) | AI plus human-supported maintenance service alternative |
| C13 | [Checkatrade](https://www.checkatrade.com/) | UK contractor-discovery context; no universal integration/booking API established |

TrustATrader, Rated People and direct Lula material did not yield sufficient reliable API detail in this research. Their access/booking capabilities remain UNKNOWN; this is not evidence they lack integrations. Lula's relevance is supported by AppFolio's own page.

## Gemini and Pydantic AI — DOC

| ID | Source | Use |
|---|---|---|
| G01 | [Gemini models](https://ai.google.dev/gemini-api/docs/models) | Current model availability catalog; account entitlement separate |
| G02 | [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) | Exact selected model/capabilities/thinking options |
| G03 | [Function calling](https://ai.google.dev/gemini-api/docs/function-calling) | Provider tool interface |
| G04 | [Structured output](https://ai.google.dev/gemini-api/docs/structured-output) | Schema output support and limitations |
| G05 | [Pricing](https://ai.google.dev/gemini-api/docs/pricing) | Dated prices/free-tier listing; no hackathon grant guarantee |
| P01 | [Agent](https://pydantic.dev/docs/ai/core-concepts/agent/) | Typed model execution loop |
| P02 | [Dependencies](https://pydantic.dev/docs/ai/core-concepts/dependencies/) | deps_type / RunContext |
| P03 | [Function tools](https://pydantic.dev/docs/ai/tools-toolsets/tools/) | Contextual/plain tools and schemas |
| P04 | [Toolsets](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/) | Tool grouping |
| P05 | [Output](https://pydantic.dev/docs/ai/core-concepts/output/) | ToolOutput, output validation and retries |
| P06 | [Google model provider](https://pydantic.dev/docs/ai/models/google/) | GoogleModel/provider integration |
| P07 | [Graph](https://pydantic.dev/docs/ai/graph/graph/) | Typed graph execution versus domain dependency data |
| P08 | [Durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/) | Supported runtime integrations and durability distinction |
| P09 | [Harness](https://pydantic.dev/docs/ai/harness/) | Current official 2026 agent/harness capabilities, separate package |
| P10 | [Logfire](https://pydantic.dev/docs/ai/integrations/logfire/) | Optional tracing |
| P11 | [Testing](https://pydantic.dev/docs/ai/guides/testing/) | Controlled model tests |
| P12 | [Evals](https://pydantic.dev/docs/ai/evals/evals/) | Optional scenario evaluation tooling |
| P13 | [Pydantic unions](https://pydantic.dev/docs/validation/latest/concepts/unions/) | Discriminated application action model |

Older `ai.pydantic.dev` links redirected to current `pydantic.dev/docs` routes during research. Use the current docs and installed package version together; examples from earlier releases may differ.

## ElevenLabs — DOC

| ID | Source | Use |
|---|---|---|
| V01 | [Agents overview](https://elevenlabs.io/docs/agents-platform/overview) | Voice/conversation architecture; redirects to current ElevenAgents documentation |
| V02 | [Webhook/server tools](https://elevenlabs.io/docs/eleven-agents/customization/tools/webhook-tools) | In-conversation backend actions and tool authentication |
| V03 | [Dynamic variables](https://elevenlabs.io/docs/eleven-agents/customization/personalization/dynamic-variables) | Session context and provider identifiers |
| V04 | [Twilio native integration](https://elevenlabs.io/docs/eleven-agents/phone-numbers/twilio-integration/native-integration) | Purchased number versus verified caller-ID constraints |
| V05 | [Twilio personalization](https://elevenlabs.io/docs/eleven-agents/customization/personalization/twilio-personalization) | Inbound initiation context |
| V06 | [SIP trunking](https://elevenlabs.io/docs/eleven-agents/phone-numbers/sip-trunking) | Alternative telephony route |
| V07 | [Outbound Twilio API](https://elevenlabs.io/docs/api-reference/integrations/twilio/outbound-call) | Initiation request and nullable provider IDs |
| V08 | [Post-call webhooks](https://elevenlabs.io/docs/eleven-agents/workflows/post-call-webhooks) | Event types, envelope, signature verification and acknowledgment |
| V09 | [Privacy](https://elevenlabs.io/docs/eleven-agents/customization/privacy) | Audio saving and retention settings |
| V10 | [Conversation analysis](https://elevenlabs.io/docs/eleven-agents/customization/agent-analysis) | Structured extraction/evaluation, separate from transcript |
| V11 | [Conversation details](https://elevenlabs.io/docs/api-reference/conversations/get) | Transcript, status, audio flags and metadata recovery |
| V12 | [Conversation audio](https://elevenlabs.io/docs/api-reference/conversations/get-audio) | Actual audio retrieval endpoint |
| V13 | [React SDK](https://elevenlabs.io/docs/eleven-agents/libraries/react) | Browser startSession, conversation ID, WebSocket signed URL versus WebRTC token |

The account-specific settings and a successful recorded call still require implementation-time verification. Documentation availability is not proof this account has been configured.

## Research, hosting and UI — DOC unless noted

| ID | Source | Use |
|---|---|---|
| T01 | [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search) | Bounded evidence search |
| T02 | [Tavily Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract) | Selected-page content |
| T03 | [Tavily Crawl](https://docs.tavily.com/documentation/api-reference/endpoint/crawl) | Assessed and excluded |
| T04 | [Tavily Map](https://docs.tavily.com/documentation/api-reference/endpoint/map) | Assessed and excluded |
| T05 | [Tavily Pydantic AI integration](https://docs.tavily.com/documentation/integrations/pydantic-ai) | Existing helper, with custom domain wrapper selected |
| T06 | [Google Places Text Search](https://developers.google.com/maps/documentation/places/web-service/text-search) | Structured business-discovery alternative |
| M01 | [Modal guide](https://modal.com/docs/guide) | Hosted Python compute |
| M02 | [Modal job queues](https://modal.com/docs/guide/job-queue) | Spawned invocation/result lifecycle |
| M03 | [Modal schedules](https://modal.com/docs/guide/cron) | Period/Cron functionality |
| M04 | [Conduct](https://conduct.ai) | VENDOR: enterprise-software product; no maintenance integration established |
| S01 | [SQLite WAL](https://sqlite.org/wal.html) | Single-writer/shared-host constraints |
| S02 | [SQLAlchemy versioning](https://docs.sqlalchemy.org/en/20/orm/versioning.html) | Optimistic versioning and bulk-update limitations |
| S03 | [FastAPI background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) | Post-response tasks; not our durable job ledger |
| S04 | [Supabase database](https://supabase.com/docs/guides/database/overview) | Managed PostgreSQL alternative |
| S05 | [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/) | Development tunnel limitations, including no SSE |
| U01 | [React Flow](https://reactflow.dev/learn) | Work-order dependency visualization |
| U02 | [Vite](https://vite.dev/guide/) | Frontend build/development stack |
| U03 | [shadcn](https://ui.shadcn.com/docs) | UI component approach |

## Research limitations and refresh policy

Public pages cannot prove competitors lack a feature, actual supplier capacity, commercial demand for this product, or event rules that have not been published. Where extraction failed, findings remain LIMITED/UNKNOWN. Vendor feature claims were treated as claims, and no vendor ROI/accuracy statistic was adopted as our evidence.

Refresh event rules at check-in; model/access/pricing and SDK contracts at implementation; emergency/legal/data-protection guidance before any real pilot; competitor claims before making a public uniqueness claim. Preserve the research date and any material corrections in 26.
