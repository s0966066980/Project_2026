# Smart Ordering

This context describes the customer-ordering and store-operations concepts shared by the kiosk, Admin, and backend.

## Runtime Language

**Runtime Persistence Profile**:
The single configuration and evidence interface that selects the relational database adapter, database topology, guarded runtime data root, credentials, connection behavior, schema state, and deployment readiness. Domains own transaction intent while this module owns connection and pool mechanics; its Traditional Chinese display term is 「執行期持久化設定檔」.
_Avoid_: Member storage backend, Database port switch, JSON fallback

**Local Single-Host PostgreSQL Runtime**:
The current developer-operated deployment in which PostgreSQL 18 runs on one local host, listens only on loopback, and stores its data and WAL archive in private directories distinct from objects, RAG indexes, backups, logs, imports, exports, SQLite, and temporary files. It supports local functional validation but is not high availability or disaster recovery; its Traditional Chinese display term is 「本機單節點 PostgreSQL 執行環境」.
_Avoid_: Production database, HA cluster, Managed PostgreSQL

**Local Pilot Readiness**:
The evidence-backed state in which the Local Single-Host PostgreSQL Runtime has passed every required runtime, contract, customer-transaction, intelligent-capability, and operational-recovery gate for controlled use in one store. It is invalidated when a changed dependency makes an affected gate's evidence stale, and it is not evidence of production high availability; its Traditional Chinese display term is 「本機試營運就緒狀態」.
_Avoid_: Process alive, Local Development Runtime, Production readiness, Configured-only readiness

**HA PostgreSQL Runtime**:
The future production topology of one primary, one synchronous standby, and one asynchronous standby on three cloud VMs in three availability zones. Its readiness requires observed PostgreSQL replication evidence; a configured topology label alone is insufficient. Cloud provisioning and failover are outside the Local Single-Host PostgreSQL Runtime; its Traditional Chinese display term is 「高可用 PostgreSQL 執行環境」.
_Avoid_: Single-host replica, Configured-only HA, Current local runtime

**Runtime Data Root**:
The guarded directory outside the Git repository beneath which each mutable data class has a private, non-overlapping subdirectory and explicit writer. It is selected only by `RUNTIME_DATA_ROOT`; its Traditional Chinese display term is 「執行期資料根目錄」.
_Avoid_: Repository data folder, Shared writable directory, Home directory

**Local Development Runtime**:
The non-commercial development boundary used by this workspace. Kiosk requests may use the development device principal without a provisioned device credential, while Admin manager capabilities still require a password-authenticated manager session. It is not evidence that the system is ready for a secured pilot or production deployment; its Traditional Chinese display term is 「本機開發展示環境」.
_Avoid_: Secured pilot, Production runtime, Public deployment

**Staff Mode**:
The default Admin surface presented without a password to a store device that holds a valid Kiosk device credential. It carries only [[Catalog Availability]] changes and scoped recommendation-effectiveness capability, and never [[Store Menu Item]] authoring (create, edit, image upload, or retirement), member records, campaigns, operational health, knowledge governance, emotion diagnostics, runtime settings, or diagnostics. A device credential is never a substitute for manager capability; its Traditional Chinese display term is 「員工模式」.
_Avoid_: Anonymous Admin, Unauthenticated Admin, Manager session, Kiosk customer surface, Catalog editor

**Manager Mode**:
The Admin surface unlocked by a password-authenticated manager session on top of Staff Mode. Leaving it returns the device to Staff Mode rather than to a locked page. Only Manager Mode may author [[Store Menu Item]] records and upload menu images; its Traditional Chinese display term is 「主管模式」.
_Avoid_: Admin login gate, Staff Mode, Device credential

**Manager LLM Debug Access**:
The Admin-only capability for listing configured models and running diagnostic prompts. It requires a password-authenticated manager session with `system.debug`; staff mode must not expose or execute it. This is distinct from customer-facing AI assistance, which follows the Kiosk request boundary; its Traditional Chinese display term is 「主管 LLM 測試權限」.
_Avoid_: Staff LLM access, Customer AI permission, Public model test

**UI API Python Runtime**:
The single supported local Python environment for the Kiosk, Admin, API, voice, and RAG services: the Conda environment named `emotion_ui`. Startup scripts, documentation, dependency checks, tests, and maintenance commands activate or explicitly execute within this environment rather than relying on an ambient shell Python or a project `.venv`; its Traditional Chinese display term is 「UI API Python 執行環境」.
_Avoid_: Ambient Python, Project .venv, Per-feature UI environments

**Text Model Routing Policy**:
The store's persisted choice of how text-model requests use the local and cloud halves of the provider chain: local-first, cloud-first, local-only, or cloud-only. It is one setting governing every text-model caller — voice assistance, emotion extraction, and Admin-side authoring of [[AI Push Copy]] — and local-only is the only value under which no customer utterance leaves the store. Serving push copy is not a caller, because it is looked up rather than generated. It is not a provider name and not a per-caller choice; its Traditional Chinese display term is 「文字模型選路策略」.
_Avoid_: AI provider toggle, Model picker, Per-feature model choice, Streaming-only exception

**Cloud Text Provider**:
NVIDIA NIM, the one external service filling the cloud half of the chain. It is fixed rather than chosen — no persisted setting selects a provider, only whether the [[Text Model Routing Policy]] admits cloud at all — and it is only reached when the policy does, with configuring cloud never implying it can serve. Naming it for a single [[Diagnostic Provider Override]] is not selecting it, because that names nothing that outlives the request; its Traditional Chinese display term is 「雲端文字提供者」.
_Avoid_: Persisted provider field, Provider setting, Gemini, OpenAI-compatible endpoint, Configured-means-working

**Diagnostic Provider Override**:
The provider and model a manager holding [[Manager LLM Debug Access]] names for one diagnostic prompt. It is never persisted, never consulted by customer traffic, and never changes the [[Text Model Routing Policy]] for any other caller — it exists so that one half of the chain can be exercised in isolation, which is the only way to tell an unready half apart from a policy that never reaches it. It must name a half that exists: an absent or unrecognised provider is refused rather than resolved into the local runtime, because a diagnostic that quietly answers from somewhere else reports the opposite of what happened; its Traditional Chinese display term is 「診斷提供者覆寫」.
_Avoid_: Provider setting, Per-caller model choice, Default provider, Fallback to local

**NIM Model Catalog**:
The developer-maintained, hardcoded set of NVIDIA NIM model IDs Admin offers in the model dropdown for each of `NIM_MODEL_NAME` and `NIM_VOICE_MODEL` — a separate, smaller catalog for the voice half. Admin cannot switch the Cloud Text Provider itself through this catalog, only which model that provider runs; its Traditional Chinese display term is 「NIM 模型目錄」.
_Avoid_: Cloud provider list, Live NVIDIA catalog fetch, Provider dropdown

**Custom NIM Model Entry**:
A model ID an administrator adds beyond the NIM Model Catalog, persisted in the settings document (`NIM_CUSTOM_TEXT_MODELS` / `NIM_CUSTOM_VOICE_MODELS`) and appended to that dropdown for every future admin session. It is saved verbatim and never validated against NVIDIA's actual catalog, so an administrator can save a model ID NVIDIA does not serve; its Traditional Chinese display term is 「自訂 NIM 模型項目」.
_Avoid_: One-time free-text override, Validated model name, Catalog entry

**Provider Readiness**:
The evidence that a half of the provider chain can actually answer: the local runtime is reachable, and the selected Cloud Text Provider has its credential present in the environment. A policy is degraded only when a half it relies on is unready. Readiness is observed, never inferred from settings, and a saved provider choice is not readiness; its Traditional Chinese display term is 「提供者就緒狀態」.
_Avoid_: Saved provider, Enabled flag, Successful save

**Provider Credential**:
The secret authorising one provider, held only in the environment and named by its variable. It is never accepted, stored, versioned, returned, or broadcast by the settings surface, which reports only whether it is present. Rotating one is a deployment action, not a settings change; its Traditional Chinese display term is 「提供者憑證」.
_Avoid_: Settings field, Admin-entered key, Masked value in settings

**R1-Omni Emotion Runtime**:
The sole local emotion-inference runtime used by the store. When it is unavailable, affected emotion diagnostics are disabled explicitly and no alternate emotion model is selected; its Traditional Chinese display term is 「R1-Omni 情緒執行環境」.
_Avoid_: Emotion Runtime Profile, Alternate emotion runtime, Emotion provider selector, Automatic provider fallback

**Emotion Provider Readiness**:
Runtime evidence that the [[R1-Omni Emotion Runtime]] has loaded its model, identifies itself, and declares the media or audio input capabilities required by the requested Admin or Voice flow. A Text-to-Speech Emotion Simulation additionally requires its configured TTS provider to be ready. An open network port alone is not readiness. A failed handshake disables the affected emotion diagnostics with an explicit reason but does not prevent UI API, ordering, or checkout from starting; its Traditional Chinese display term is 「情緒模型就緒狀態」.
_Avoid_: Port open, Configured provider name, Process alive

**Emotion Model Observation**:
The authoritative structured result produced by the [[R1-Omni Emotion Runtime]] for one evidence capture. It identifies the model version, evidence mode and capture identity, transcript presence, emotion and intensity, facial and vocal evidence summaries when available, description, model-native confidence when supplied, and latency. It never exposes model chain-of-thought, and missing confidence is reported as not provided rather than invented; its Traditional Chinese display term is 「情緒模型觀測」.
_Avoid_: Generic LLM answer, Emotion explanation, Fused model result, Raw model reasoning

**Emotion Diagnostic Acceptance Set**:
A fixed, balanced, non-customer collection of labeled audio-only and live-media samples used to verify the selected provider against the operational emotion labels Neutral, Happy, Frustrated, Anxious, Confused, and Angry. It is acceptance evidence rather than training material, and its Traditional Chinese display term is 「情緒診斷驗收集」.
_Avoid_: Customer recording archive, Training corpus, Provider health check, Free-form emotion labels

**Admin Emotion Diagnostic Record**:
A store-scoped durable record retained for 30 days to audit an Admin emotion diagnostic. It contains the structured Emotion Model Observation, provider and model version, evidence mode, capture identity or irreversible fingerprint, timestamps, readiness identity, and latency. When Emotion Observation Explanation succeeds, the exact customer-emotion summary and staff response recommendation shown in Admin are retained with the configured LLM and prompt versions. Raw image, video, audio, and transcript content are excluded and discarded after inference; its Traditional Chinese display term is 「管理端情緒診斷紀錄」.
_Avoid_: Raw media archive, Transcript history, Training corpus, Permanent diagnostic log

## Store Catalog Language

**Store Menu Item**:
A sellable product that belongs to exactly one store: customer-facing name, category label, price, description, image, and [[Catalog Availability]]. Its identity is store-scoped and stable after creation; runtime ordering, pricing, and recommendations read only the active (non-retired) items for that store. Its Traditional Chinese display term is 「店舖菜單品項」; Admin UI may say 「商品」.
_Avoid_: Global menu.json entry, Knowledge Item, Campaign, Cross-store shared SKU master

**Menu Category Label**:
The free-text classification string on a [[Store Menu Item]] used to group the product workbench and kiosk browsing. Categories are not a separate managed entity; the set shown in filters is the distinct labels of active items in that store. Creating an item with a new label is how a category appears. Its Traditional Chinese display term is 「商品類別」.
_Avoid_: Category master data, Fixed enum, Knowledge Category

**Catalog Availability**:
The operational sellability overlay on a [[Store Menu Item]] for its store: normal, low stock, sold out, or disabled, plus store service-period rules that can mark breakfast items time-unavailable. It is not retirement and not a price change. Staff Mode may change it; its Traditional Chinese display term is 「供應狀態」.
_Avoid_: Menu deletion, Stock ledger, Inventory count

**Menu Item Retirement**:
The soft-removal of a [[Store Menu Item]] from the sellable catalog. Retired items are hidden from kiosk and new orders, remain addressable for history and admin recovery, and are distinct from disabled (still listed, temporarily not sold). Only Manager Mode may retire or restore; its Traditional Chinese display term is 「商品退役」.
_Avoid_: Hard delete, Sold out, Disabled, Knowledge Deletion

**Menu Item Image**:
The single customer-facing picture for a [[Store Menu Item]], either an uploaded binary normalized by the server into object storage or an external http(s) URL kept for import compatibility. Upload replaces the prior image reference for that item; its Traditional Chinese display term is 「商品圖片」.
_Avoid_: Kiosk emoji fallback as source of truth, Unprocessed original upload as served asset

## Customer Ordering Language

**Ordering Entry Flow**:
A store- and device-scoped customer entry sequence with a stable `entry_flow_id`. The startup screen first presents one 「開始點餐」 action; selecting it loads a versioned Ordering Entry Policy and opens the ordering-mode choice, where the customer chooses either 「會員登入」 or 「訪客點餐」 before an Ordering Session is created and the menu is initialized. Membership is not a separate action on the startup screen. Policy loading may block this transition for at most three seconds; on failure or timeout, the ordering-mode choice remains available by default. It is skipped only when the policy loads successfully and explicitly disables member entry. At most one Entry Flow is active per Kiosk device, and reload or retry resumes that flow rather than creating another.
_Avoid_: Separate startup login, Automatic guest ordering

**Ordering Entry Policy**:
The immutable, versioned store policy snapshot that controls entry choices for one Ordering Entry Flow. Ordinary policy changes affect new flows only; emergency ordering availability is a separate gate. Its Traditional Chinese display term is 「點餐入口政策」.
_Avoid_: Runtime settings blob, Mid-flow UI switch, Store availability

**Member Login Service Failure**:
A technical failure while checking a customer's phone number. It keeps the customer on the login screen and offers 「重試」 and 「訪客點餐」; it is distinct from a successful lookup that confirms the phone number is not registered and must never open registration automatically.
_Avoid_: Member not found, Automatic registration

**Member Registration Service Failure**:
A technical failure after a customer submits registration. It keeps the entered phone number, nickname, and consent state on the registration screen, explains that registration was not completed, and offers 「重試」 and 「訪客點餐」. It never silently starts a guest order.
_Avoid_: Successful registration, Automatic guest fallback

**Menu Initialization Failure**:
A recoverable failure after the customer has chosen member or guest ordering but before the menu becomes usable. The kiosk shows 「重試」 and 「返回點餐方式」 without reloading the page, while preserving authenticated member state and entered member data.
_Avoid_: Blank menu, Forced page reload

**Checkout Quote**:
An immutable, server-authored snapshot of the authoritative cart, item prices, applied promotions, fees, total, and validity presented to the customer before order creation. The kiosk displays this snapshot without recalculating its commercial values, and confirmation references its `quote_id` rather than resubmitting client-priced cart contents; its Traditional Chinese display term is 「結帳報價」.
_Avoid_: Client cart total, Order, Payment receipt

**Order Confirmation**:
The successful creation of an Order from a valid Checkout Quote after atomic fulfillment validation. It proves that the order was accepted, not that payment was collected; its Traditional Chinese display term is 「訂單確認」.
_Avoid_: Checkout log, Payment success, Completion telemetry

**Payment Pending**:
The state of a confirmed Order whose payment still requires provider or counter completion. Manual payment remains Payment Pending until an explicit payment result marks it Paid or Failed; its Traditional Chinese display term is 「待付款」.
_Avoid_: Paid, Order confirmation failure, Assumed counter payment

**Confirmation Outcome Unknown**:
The Kiosk state after submitting Confirm Checkout when transport failure prevents it from knowing whether the Order was created. The Kiosk preserves the Checkout Quote and idempotency key and queries or retries with that same identity until it finds the Order or receives an authoritative rejection; it never treats uncertainty as failure or starts a second confirmation. Its Traditional Chinese display term is 「訂單確認結果未知」.
_Avoid_: Checkout failed, Retry with new key, Duplicate order

## Voice Ordering Language

**Fixed Voice Language Policy**:
The Kiosk UI, speech recognition, voice-assistant text, and synthesized speech use Traditional Chinese only. Voice turns do not expose a language selector, detect a response language, or carry an English prompt/voice setting; its Traditional Chinese display term is 「固定語音語言政策」.
_Avoid_: Voice language switching, automatic response-language detection, English voice reply

**Voice Turn**:
A single customer voice interaction with a stable `voice_turn_id` scoped to its store and ordering session. It begins when the customer taps the voice control, listens without requiring the control to be held, and submits automatically after detected speech followed by 1.5 seconds of silence. It ends as no recognizable speech when speech has not begun within 8 seconds and may record for at most 30 seconds. While listening, visible 「立即送出」 and 「取消」 controls remain available as manual recovery paths. Every Voice Turn reaches exactly one visible terminal outcome: completed, cancelled, no recognizable speech, permission unavailable, recording failure, transcription failure, assistant failure, or playback degradation. Retrying the same `voice_turn_id` resumes or replays that Voice Turn and never creates a second assistant execution, Voice Order Draft, or Voice Emotion Observation request; its Traditional Chinese display term is 「語音回合」.
_Avoid_: Hold-to-talk, Indefinite recording, Voice session

**Voice Media Degradation**:
The fallback boundary that keeps a Voice Turn available with microphone input alone when camera permission, capture, or emotion-video analysis is unavailable. Camera-derived emotion is optional enrichment and must never block recording, transcription, assistant execution, or ordering; its Traditional Chinese display term is 「語音媒體降級」.
_Avoid_: Camera-required voice, Combined camera-and-microphone failure

**Voice Emotion Observation**:
An asynchronous optional enrichment derived from a completed Voice Turn. It never delays or changes the Voice Turn that produced it; once complete, it may inform a later Voice Turn under the assistance policy or remain operational evidence. Its Traditional Chinese display term is 「語音情緒觀測」.
_Avoid_: Synchronous voice prerequisite, Current-turn emotion gate, Customer emotion diagnosis

**Voice Playback Degradation**:
A terminal Voice Turn outcome in which transcription and assistant execution succeeded but synthesized-audio playback did not. The kiosk preserves and displays the text response and any Voice Order Draft, and explicitly reports that voice playback is temporarily unavailable; its Traditional Chinese display term is 「語音播放降級」.
_Avoid_: Assistant failure, Silent playback failure, Discarded text response

**Voice Response Wait**:
The customer-perceived interval from the customer's last detected speech to the first perceivable assistant response, whether visible text or audible speech. Its P95 target is at most three seconds and optional enrichment such as camera emotion analysis is outside this critical interval; its Traditional Chinese display term is 「語音回覆等待」.
_Avoid_: Full-response duration, API response-header latency, Emotion-analysis completion time

**Progressive Voice Response**:
A Voice Turn response that displays validated assistant text as soon as it becomes available and begins synthesized speech afterward without withholding the text. Text is the first response surface; audio remains a following enhancement and may degrade independently. Its Traditional Chinese display term is 「漸進式語音回覆」.
_Avoid_: Processing placeholder, Audio-gated text, Unvalidated JSON fragment

**Voice Menu Candidate Set**:
The small request-specific set of menu items selected by names, aliases, and retrieval signals for one Voice Turn. The voice LLM reasons only over this set rather than the full store menu, while the server remains authoritative for item IDs, prices, availability, and proposed order items. When no candidate is sufficiently reliable, the kiosk presents a few similar items for explicit customer selection instead of loading the full menu or guessing an order item; its Traditional Chinese display term is 「語音菜單候選集」.
_Avoid_: Full menu prompt, Unvalidated LLM menu, RAG knowledge result

**Voice Order Draft**:
A non-transactional set of proposed menu items and quantities produced from a Voice Turn. The kiosk displays every confidently matched item in a dedicated confirmation modal, initially unchecked, and displays ambiguous mentions separately with two or three unselected similar items. The customer may adjust quantities, select related recommendations, and choose which draft items to include. No item enters the cart until the customer presses 「確認加入購物車」; only checked items are added, cancellation leaves the cart unchanged, and only one Voice Order Draft may await confirmation before another Voice Turn begins. Its Traditional Chinese display term is 「語音點餐草稿」.
_Avoid_: Voice cart action, Automatic add to cart, Confirmed order

**Voice Model Warm State**:
The runtime condition in which the configured local voice LLM has been loaded before the kiosk accepts Voice Turns and is kept resident for the configured interval. Model loading belongs to service readiness rather than the first customer's Voice Response Wait; its Traditional Chinese display term is 「語音模型預熱狀態」.
_Avoid_: First-customer warm-up, Permanent GPU assumption, STT warm state

**Live Admin Emotion Test**:
An isolated Admin diagnostic that models one real customer observation through a single adaptive capture flow against the [[R1-Omni Emotion Runtime]]. Media is the primary evidence. With no detected speech it submits a two-second media observation; when speech is detected it automatically transcribes only the audio from that same capture and supplies the aligned transcript as supporting evidence. If speech is detected but transcription fails, the same media observation still proceeds and records `transcript_unavailable` rather than accepting replacement text. The Admin cannot select or change the emotion runtime, manually supply a transcript, or choose A/B evidence schemes; its Traditional Chinese display term is 「管理端即時情緒測試」.
_Avoid_: Emotion provider selector, Manual transcript, Scheme A/B selector, Production profile setting, Kiosk intervention

**Text-to-Speech Emotion Simulation**:
An Admin diagnostic that converts operator-entered simulated customer speech into synthetic audio through the configured TTS provider, then supplies that audio—not the source text—to the [[R1-Omni Emotion Runtime]]. Every input uses one fixed neutral voice, speaking rate, volume, and prosody so the diagnostic primarily probes emotion inference from spoken semantic content rather than a TTS-selected emotion. It produces a simple Emotion Model Observation and tests the audio emotion-analysis path without image or live-capture evidence; its Traditional Chinese display term is 「文字模擬情緒測試」.
_Avoid_: Direct text classification, Emotional TTS preset, Live image test, Generic LLM prompt, Independent text assistant

**Validated Audio-Only Emotion Capability**:
A provider capability declared only after its explicit audio-only inference contract passes controlled comparisons covering the same semantic content with differing prosody and differing semantic content with the same neutral prosody. Text-to-Speech Emotion Simulation remains disabled for a provider until this capability is validated; wrapping synthetic audio in a blank video does not qualify. Its Traditional Chinese display term is 「已驗證純音訊情緒能力」.
_Avoid_: Assumed Whisper capability, Blank-video wrapper, Port readiness, Experimental result presented as reliable

**Emotion Observation Explanation**:
An Admin-facing second-stage summary and staff response recommendation generated by the configured default LLM from only the authoritative emotion classification and provider-authored textual analysis in one Emotion Model Observation. The LLM does not receive raw media or transcript content, must preserve the provider's emotion classification, and may not independently reclassify or override it. The UI displays the source model observation separately from this downstream advice. If the configured LLM fails or times out, the successful model observation remains valid and visible while advice is marked unavailable; the system does not switch LLMs. Its Traditional Chinese display term is 「情緒觀測解說」.
_Avoid_: Primary emotion classification, Raw media prompt, Transcript prompt, Hidden emotion override, Model observation merged with advice

**Live Emotion Test Cadence**:
The Admin test loop that permits only one observation batch in flight and captures an adaptive evidence window. With no detected speech it completes a two-second media-only capture; once speech begins it keeps the same media and audio capture through 1.5 seconds of silence, up to ten seconds, so the provider can receive a temporally aligned transcript as supporting evidence. After a batch finishes, it analyzes the newest available capture without accumulating stale GPU work; its Traditional Chinese display term is 「即時情緒測試週期」.
_Avoid_: Fixed two-second speech clip, Concurrent polling, Frame-only inference, Unbounded analysis queue

## Campaign Language

**Campaign**:
One store-scoped promotional offer authored in Admin, carrying its own objective, audience, schedule, customer-facing placements, and exactly one promotion rule. Every change to it produces a new append-only version, and its identity survives every lifecycle change. Customer-facing activity visibility comes only from a Campaign whose lifecycle status is active or scheduled; compatibility promotion projections are not independent activities. Its Traditional Chinese display term is 「活動」.
_Avoid_: Promotion record, Banner, Discount code, Legacy promotion row

**Campaign Content**:
The authored substance of a Campaign — name, objective, audience, schedule, placements, promotion rule, and creatives. Revising it writes a new version and never moves the Campaign through its lifecycle: a paused Campaign stays paused after an edit, and no save can take a Campaign on or off air; its Traditional Chinese display term is 「活動內容」.
_Avoid_: Draft save that unpublishes, Campaign status, Live edit

**Campaign Lifecycle Status**:
The single position a Campaign occupies among draft, review, scheduled, active, paused, ended, and archived. Only an explicit lifecycle action moves it, archived is terminal, and Campaign Content is editable only while draft, review, paused, or ended; its Traditional Chinese display term is 「活動狀態」.
_Avoid_: Enabled flag, Visible/hidden, Deleted

**Campaign Publication**:
The one operation that validates Campaign Content, stores it as a version, and puts the Campaign on air — as scheduled when its start time is still ahead in store time, as active when it is already due. It is a single request completed by the server, so an operator never holds an intermediate version, and it applies only to a Campaign that is still draft or review; its Traditional Chinese display term is 「活動發布」.
_Avoid_: Publish button sequence, Client-driven transition chain, Republish of a live campaign

## Recommendation Language

**AI Push Copy**:
The single short sentence shown on the Kiosk push bar for one recommended menu item. It is authored in Admin ahead of time and resolved at request time by lookup, never generated while a customer waits, so it cannot be slow, fail, or assert a promotion the store is not running. It resolves as [[Campaign Push Copy]] when that copy's offer is currently active, otherwise [[Base Push Copy]], otherwise the menu item's own description; its Traditional Chinese display term is 「推播文案」.
_Avoid_: Generated copy, Model status, Recommendation reason, Promotion banner, Voice assistant reply

**Base Push Copy**:
The evergreen half of AI Push Copy: one sentence describing the menu item itself, valid regardless of which campaigns are running. It is required for an item to be pushed on its own merits, and is refused at save time if it contains an unverified promotional term, because authored copy reaches every customer until an operator edits it; its Traditional Chinese display term is 「常態推薦詞」.
_Avoid_: Fallback sentence, Default copy, Promotional copy

**Campaign Push Copy**:
The optional promotional half of AI Push Copy, bound to the offer it depends on rather than to a date. It is served only while that offer is among the currently active offers, so an ended campaign stops showing its copy on its own and the item reverts to [[Base Push Copy]]; its Traditional Chinese display term is 「活動推薦詞」.
_Avoid_: Copy with an expiry date, Seasonal copy, Campaign banner

**Unverified Promotion Claim**:
A discount, price, or campaign asserted in [[Base Push Copy]] that no offer supports. Because push copy is authored rather than generated, this is rejected when the operator saves it — with the offending terms named — instead of being rewritten when it is served; its Traditional Chinese display term is 「未驗證促銷聲明」.
_Avoid_: Serve-time rewrite, Model failure fallback, Verified offer copy

**Push Scope**:
The store's choice of which menu items are *eligible* for the push bar: all items, selected categories, current new items, or the most frequently carted items. It is a filter and not a ranking — whichever items survive it are still ordered by the recommendation engine, with availability, ignore-feedback and offer weighting unchanged; its Traditional Chinese display term is 「推播範圍」.
_Avoid_: Recommendation strategy, Sort order, Per-item priority

**Assistance Recommendation**:
An explicit customer request from the Kiosk assistance window for up to three currently eligible menu items. It uses the shared recommendation engine and still excludes items already in the cart or unavailable now, but it is not restricted by [[Push Scope]], which governs only the passive push bar; its Traditional Chinese display term is 「協助推薦」.
_Avoid_: Push-scope recommendation, Promotion-only recommendation, Guaranteed recommendation

**New Item Window**:
The dated period during which a menu item counts as new for [[Push Scope]]. An operator ticks the item and sets an end date, after which it stops counting without anyone having to untick it; its Traditional Chinese display term is 「新品檔期」.
_Avoid_: Permanent new flag, Menu import date, Campaign schedule

## RAG Governance Language

**RAG Readiness Workflow**:
An Admin-facing read model that composes, without taking ownership of, Store Knowledge Base publication, Published Retrieval Configuration, and Retrieval Check evidence into the ordered steps Author → Publish and Index → Configure → Test and Confirm. It reports complete, active, blocked, pending, or locked for each step and offers a recovery action when a durable Publication Attempt has lost its reliable worker job; its Traditional Chinese display term is 「RAG 就緒流程」.
_Avoid_: Shared RAG ownership interface, UI-guessed readiness, Port-only worker health, Empty result without recovery guidance

**Store Knowledge Base**:
The isolated collection of knowledge, index artifacts, Retrieval Test Cases, Evaluation Runs, and Published Retrieval Configuration owned by one store. It has no cross-store inheritance or shared knowledge; its Traditional Chinese display term is 「門市知識庫」.
_Avoid_: Global RAG, Tenant knowledge base

**Knowledge Item**:
A store-owned unit of retrieval knowledge with a title, one Knowledge Category, one RAG Content Type, Knowledge Content, versions, and publication state. Its Traditional Chinese display term is 「知識項目」.
_Avoid_: Document, RAG Doc, Asset

**Knowledge Version**:
An immutable revision of a Knowledge Item with its own content checksum and publication outcome. Corrections create a new Draft version.
_Avoid_: Editable review record

**Knowledge Edit Conflict**:
A rejected save caused by another administrator changing the same knowledge item after editing began. The competing contents are compared explicitly; neither silently overwrites the other.
_Avoid_: Locked knowledge, Last-write-wins

**Draft**:
The state a Knowledge Version occupies between being saved and its retrieval index being built. Saving publishes automatically, so this is a transient system state rather than something an operator holds knowledge in or advances by hand; it is visible only as 「索引中」. Revisions create another version that passes through it again.
_Avoid_: Unpublished work in progress, Manual publication step, Parking state

**Indexing**:
A Knowledge Version whose publication was requested and whose retrieval index is being built. It is not yet available to retrieval, and each Knowledge Item may have at most one Indexing version while newer Draft versions continue to be authored.
_Avoid_: Published, Pending

**Index Failed**:
A Knowledge Version whose retrieval index could not be built. It is not available to retrieval and may be retried.

**Publication Failed**:
A Knowledge Version whose index artifacts were built but whose atomic publication swap could not be committed. It is not available to retrieval, the previous Published version remains authoritative, and publication may be retried; its Traditional Chinese display term is 「發布失敗」.
_Avoid_: Index Failed, Published

**Publication Attempt**:
An auditable attempt to publish one Knowledge Version that records its current phase and outcome so retries can continue from the last verified success. Historical attempts are retained, but each Knowledge Item has at most one publication attempt in flight; its Traditional Chinese display term is 「發布嘗試」.
_Avoid_: Background Job, Evaluation Run

**Published**:
The single Knowledge Version currently available as authoritative retrieval source material.
_Avoid_: Active

**Retired**:
A Knowledge Version withdrawn from publication and no longer authoritative retrieval source material. It is reached on the way to [[Knowledge Deletion]] rather than offered as an action of its own, because a store's list of knowledge is only trustworthy when what it shows is what is live.
_Avoid_: Archived, Standalone withdraw action

**Knowledge Deletion**:
The permanent removal of a Knowledge Item, its versions and its retrieval index entries. The index is cleaned first — deleting only the record would leave its chunks retrievable with nothing owning them — and the publication audit trail is deliberately kept, so who deleted what and when stays answerable. Deleting knowledge that a [[Expected Knowledge]] reference depends on is permitted, but the affected Retrieval Test Cases are named and confirmed first; its Traditional Chinese display term is 「知識刪除」.
_Avoid_: Retire, Soft delete, Hide from list

**Knowledge Category**:
A controlled business-topic classification selected through the Admin UI. Every knowledge item has exactly one primary category—Store and Hours, Menu and Products, Promotions, Payment and Invoice, Membership, Order and Pickup, Delivery, Nutrition and Allergens, or Other—and its Traditional Chinese display term is 「知識分類」.
_Avoid_: Knowledge Type, RAG Type

**Popular Knowledge Category**:
One of the four Knowledge Categories with the most Published knowledge items in the current store. Draft, Retired, and other-store knowledge never affects its rank.
_Avoid_: Recommended category, Global category

**RAG Content Type**:
The structural form of knowledge: Knowledge Article, Question and Answer, Policy Rule, or Operating Procedure. Every type uses the same Knowledge Content model rather than type-specific structured fields; its Traditional Chinese display term is 「RAG 內容類型」.
_Avoid_: Knowledge Category, Retrieval Method

**Retrieval Method**:
The store-level algorithm used to find indexed knowledge: BM25, Dense Vector, Hybrid RRF, or Hybrid with Reranker. Tests may compare all methods, but a store has exactly one Published Retrieval Method for customer-facing retrieval; its Traditional Chinese display term is 「檢索方法」.
_Avoid_: RAG Type, Knowledge Category

**Retrieval Configuration**:
A versioned store-level combination of a Retrieval Method, Top K, and Relevance Policy with its publication evidence. An authorized administrator may permanently delete any version; deleting the Published version leaves the store without a Published Retrieval Configuration until another is published.
_Avoid_: Per-document RAG settings, Model tuning

**Relevance Policy**:
A method-calibrated minimum-result policy selected as Lenient, Balanced, or Strict. It hides incomparable raw BM25, vector, and reranker score thresholds while preserving their versioned values.
_Avoid_: Shared score threshold, Confidence level

**Knowledge Content**:
The plain-language information contained in a Governed Document and used as retrieval source material.
_Avoid_: Structured FAQ fields

**Knowledge Title**:
An optional Admin-facing label for a knowledge item. If omitted, it is derived from the first non-empty line of Knowledge Content and is not itself authoritative retrieval content.
_Avoid_: Question field, Document ID

**Knowledge Chunk**:
A retrieval unit produced automatically from Knowledge Content according to its RAG Content Type. Administrators preview chunks before publication but do not configure chunk size or overlap.
_Avoid_: Knowledge item, Manual excerpt

**Knowledge Import Batch**:
A validated, atomic CSV upload that creates store-scoped knowledge items using the same title, category, content type, and content model as single-item authoring, and publishes every row it creates. If any row is invalid, no rows are created — that all-or-nothing validation is what makes publishing on import safe, since the content reaching customers has passed the same checks single-item authoring applies.
_Avoid_: Document upload, Index import, Staged import awaiting review

**Knowledge Publication Batch**:
A group of knowledge items indexed together but completed independently, raised automatically by a save or an import rather than assembled by hand. Successful items become Published while failed items become Index Failed and may be retried individually without rolling back the successful ones.
_Avoid_: Operator-selected publish queue, Atomic publication

**Knowledge Duplicate**:
Knowledge Content that is identical to an existing item in the same store and therefore cannot be created again. Semantic near-duplicates produce a reviewable warning but are not automatically rejected.
_Avoid_: Similar category, Shared knowledge

## RAG Evaluation Language

**Ad Hoc Retrieval Check**:
A one-time store-scoped question run against the current Published index using an explicitly selected Retrieval Method and Top K. It is not saved and produces no evaluation metrics; only the displayed immutable result snapshot produced without fallback using the current Published Retrieval Configuration may be confirmed as RAG Readiness evidence, and that evidence expires when the Published index or configuration changes; its Traditional Chinese display term is 「臨時檢索確認」.
_Avoid_: Retrieval Test Case, Evaluation Run, 即時檢索測試

**RAG Readiness Confirmation**:
Durable store-scoped proof that an authorized administrator reviewed one eligible Ad Hoc Retrieval Check result. It records the administrator, confirmation time, Published index and Retrieval Configuration identities, result fingerprint, and result count without retaining the raw question or full results; its Traditional Chinese display term is 「RAG 就緒確認」.
_Avoid_: Retrieval Test Case, Evaluation Result, Confirmed Test Timestamp

**Retrieval Test Case**:
A saved store-scoped customer question paired with one or more same-category Expected Knowledge alternatives. A hit on any alternative is sufficient, questions requiring multiple categories are split into separate cases, and its Traditional Chinese display term is 「檢索測試案例」.
_Avoid_: Ad hoc query, Prompt

**Retrieval Test Case Revision**:
An immutable change to a test question, its Expected Knowledge, or enabled state. New Evaluation Runs use the latest enabled valid revision while historical runs retain their snapshots.
_Avoid_: Edited evaluation result, Deleted test history

**Test Case Import Batch**:
An atomic CSV upload of test questions and same-category Published Expected Knowledge IDs. If any reference or row is invalid, no Retrieval Test Cases are created.
_Avoid_: Knowledge Import Batch, Evaluation Run

**Expected Knowledge**:
The stable knowledge items an administrator has marked as relevant for a Retrieval Test Case, independent of Document Version. Retiring an expected item makes the case invalid until its expectation is replaced or the case is disabled; its Traditional Chinese display term is 「預期知識」.
_Avoid_: Generated answer, Highest-score result

**Hit Rate@K**:
The proportion of Retrieval Test Cases for which at least one Expected Knowledge item appears within the first K results. An ad hoc query has no hit-rate outcome.
_Avoid_: Similarity score, Confidence

**Mean Reciprocal Rank@5**:
The average reciprocal rank of the first Expected Knowledge item found within the first five results. It rewards methods that place relevant knowledge nearer the top.
_Avoid_: Hit Rate, Similarity score

**Evaluation Run**:
A retrieval-only, immutable background comparison that snapshots one store's index, Retrieval Test Cases, and candidate Retrieval Configurations, then records quality metrics and latency. It may be cancelled, never generates an AI answer, disables production fallback, and its advisory ranking never changes production automatically; its Traditional Chinese display term is 「評估作業」.
_Avoid_: RAG test query, Automatic rollout

**Evaluation Benchmark**:
The fixed comparison profile that retrieves ten candidates under the Balanced Relevance Policy and computes Hit Rate@1, Hit Rate@3, Hit Rate@5, and Mean Reciprocal Rank@5 for each Retrieval Method. It recommends a method, not Top K or Relevance Policy.
_Avoid_: Production Retrieval Configuration, Parameter search

**Retrieval Method Recommendation**:
An advisory ranking available only at Evaluation Readiness, ordered by Hit Rate@3, then Mean Reciprocal Rank@5, then P95 latency. Indistinguishable methods remain tied rather than receiving an arbitrary winner.
_Avoid_: Automatic selection, Published Retrieval Method

**Evaluation Readiness**:
The minimum evidence required before an Evaluation Run may recommend a Retrieval Method: twenty valid cases across at least three Knowledge Categories, with no category representing more than half of the cases. It governs recommendation claims, not whether an authorized administrator may publish a Retrieval Configuration.
_Avoid_: Evaluation success, Index health

**Online Retrieval Health**:
De-identified production statistics such as query count, zero-result rate, P95 latency, and error rate for a Published Retrieval Configuration. It has no ground truth and must never be presented as hit rate.
_Avoid_: Online hit rate, Evaluation Run

**RAG Readiness**:
The minimum operational state for customer-facing retrieval: Published knowledge, a Published Retrieval Configuration, a healthy index, and one administrator-confirmed ad hoc retrieval result. It does not require Evaluation Readiness; its Traditional Chinese display term is 「RAG 就緒狀態」.
_Avoid_: Evaluation Readiness, Recommendation eligibility
