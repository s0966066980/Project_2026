# Smart Ordering

This context describes the customer-ordering and store-operations concepts shared by the kiosk, Admin, and backend.

## Runtime Language

**Business Capability Module**:
A project-owned business slice that groups related use cases behind one independently testable interface for Kiosk, Admin, and other modules. It remains deployment-neutral: a module is not a page, endpoint, or microservice, and its Traditional Chinese display term is 「業務能力模組」.
_Avoid_: Feature endpoint, Admin module, Kiosk module, One-button service, Microservice

**Module Data Authority**:
The rule that each authoritative business record has exactly one Business Capability Module permitted to change it, even when all modules share one PostgreSQL instance. Other modules consume that data through the owner's interface, event, or read model, and its Traditional Chinese display term is 「模組資料權威」.
_Avoid_: Shared repository ownership, Cross-module write, Shared table mutation, Database-per-feature

**Capability HTTP API**:
The versioned external contract through which Kiosk, Admin, and out-of-process callers use a Business Capability Module. It translates transport concerns into the module's interface and is never used as a loopback transport between modules in the same application process; its Traditional Chinese display term is 「能力 HTTP API」.
_Avoid_: Internal localhost call, Repository endpoint, Page-specific backend, Unversioned route

**Authoritative Capability Contract**:
The one current Capability HTTP API and Capability Interface owned by a Business Capability Module. A legacy route may temporarily adapt to it during measured migration but never retains separate business rules or remains as an indefinite parallel contract; its Traditional Chinese display term is 「能力權威契約」.
_Avoid_: Permanent dual API, Legacy business logic, Frontend-specific contract, Unmeasured compatibility route

**Capability Interface**:
The sole in-process contract a Business Capability Module exposes to another module, hiding its repositories and implementation. Synchronous collaboration uses this interface while durable asynchronous consequences use events and the outbox; its Traditional Chinese display term is 「能力介面」.
_Avoid_: Direct repository import, Cross-module SQL, Internal HTTP API, Global service access

**Capability Criticality**:
The declared operational class of a Business Capability Module: Core capabilities fail closed when their invariants cannot be protected, Operational capabilities follow an explicit fallback, and Optional capabilities degrade independently without stopping core ordering. Its Traditional Chinese display term is 「能力關鍵性」.
_Avoid_: Global health flag, Every-feature optional, Silent fallback, Process-alive status

**Capability Warm-Up State**:
The condition of one Business Capability Module whose model, index, or connection has not finished loading. It makes that capability report itself unready and never delays the HTTP service from accepting requests, so an Optional capability's loading cannot withhold Core ordering or the Admin surface. A process that never began warm-up makes no readiness claim at all and loads on first use instead. It is not a global startup gate, and a health endpoint that cannot answer during it is not evidence of anything; its Traditional Chinese display term is 「能力暖機狀態」.
_Avoid_: Global startup gate, Service not started, Readiness probe failure, Blocking prewarm

**Independent Product Frontend**:
Either the Admin or Kiosk browser application, independently built and tested with ownership of its own UI/UX, state, features, styles, and bootstrap. The two applications never import each other and may share only stateless generated contracts, design tokens, primitives, and transports; its Traditional Chinese display term is 「獨立產品前端」.
_Avoid_: Runtime Admin mode, Shared feature state, Cross-product import, One frontend with two routes

**Module Independence Gate**:
The evidence threshold at which a Business Capability Module owns its contracts, data mutations, permissions, tests, failure behavior, and callers with no remaining legacy business path. Moving files or adding endpoints alone never passes it, and its Traditional Chinese display term is 「模組獨立閘門」.
_Avoid_: Folder migration complete, Endpoint exists, Legacy adapter active, Unit tests only

**Runtime Persistence Profile**:
The single configuration and evidence interface that selects the relational database adapter, database topology, guarded runtime data root, credentials, connection behavior, schema state, and deployment readiness. Domains own transaction intent while this module owns connection and pool mechanics; its Traditional Chinese display term is 「執行期持久化設定檔」.
_Avoid_: Member storage backend, Database port switch, JSON fallback

**Local Single-Host PostgreSQL Runtime**:
The current developer-operated deployment in which PostgreSQL 18 runs on one local host, listens only on loopback, and stores its data and WAL archive in private directories distinct from objects, RAG indexes, backups, logs, imports, exports, SQLite, and temporary files. It supports local functional validation but is not high availability or disaster recovery; its Traditional Chinese display term is 「本機單節點 PostgreSQL 執行環境」.
_Avoid_: Production database, HA cluster, Managed PostgreSQL

**Local Pilot Readiness**:
The evidence-backed state in which the Local Single-Host PostgreSQL Runtime has passed every required runtime, contract, customer-transaction, intelligent-capability, and operational-recovery gate for controlled use in one store. It is invalidated when a changed dependency makes an affected gate's evidence stale, and it is not evidence of production high availability; its Traditional Chinese display term is 「本機試營運就緒狀態」.
_Avoid_: Process alive, Local Development Runtime, Production readiness, Configured-only readiness

**Pilot Release Candidate**:
A versioned build proposed for a supported, single-store closed Pilot but not yet admitted for use. It becomes a Pilot release only after current evidence establishes Local Pilot Readiness for that exact build and environment, and its Traditional Chinese display term is 「試營運候選版本」.
_Avoid_: Demo build, Latest main, Production release, Untested image

**Pilot Release Artifact**:
The exact set of CI-built, digest-pinned container images admitted by a Pilot Release Candidate. Building replacement images on the Pilot host creates a different artifact and invalidates that candidate's evidence; host-provided model weights are verified separately, and its Traditional Chinese display term is 「試營運發布成品」.
_Avoid_: Local image tag, On-host build, Latest image, Git checkout

**Pilot Readiness Gate**:
An ordered admission boundary passed only by current evidence for the same Pilot Release Artifact and target environment. Closing implementation issues or assigning a completion percentage does not pass a gate, and its Traditional Chinese display term is 「試營運就緒閘門」.
_Avoid_: Project phase, Priority bucket, Checklist completion, Subjective percentage

**Product Batch Functional Acceptance**:
The evidence threshold that permits work to advance from one approved product batch to the next after that batch's promised behavior and required tests pass. It does not imply that the affected Business Capability Modules have passed the Module Independence Gate, and any remaining architecture convergence or legacy removal still belongs to Project Completion; its Traditional Chinese display term is 「產品批次功能驗收」.
_Avoid_: Module Independence Gate, Project Completion, Architecture complete, Legacy removed

**Pilot Recovery Objective**:
The accepted recovery bound for the closed single-store Pilot: authoritative data may be restored to no more than one hour before a failure, and critical ordering operations must return within four hours. It requires observed restore evidence from a backup copy separated from the primary runtime, and its Traditional Chinese display term is 「試營運復原目標」.
_Avoid_: Volume persistence, Backup command succeeded, Daily-only backup, Production disaster recovery

**HA PostgreSQL Runtime**:
The future production topology of one primary, one synchronous standby, and one asynchronous standby on three cloud VMs in three availability zones. Its readiness requires observed PostgreSQL replication evidence; a configured topology label alone is insufficient. Cloud provisioning and failover are outside the Local Single-Host PostgreSQL Runtime; its Traditional Chinese display term is 「高可用 PostgreSQL 執行環境」.
_Avoid_: Single-host replica, Configured-only HA, Current local runtime

**Runtime Data Root**:
The guarded directory outside the Git repository beneath which each mutable data class has a private, non-overlapping subdirectory and explicit writer. It is selected only by `RUNTIME_DATA_ROOT`; its Traditional Chinese display term is 「執行期資料根目錄」.
_Avoid_: Repository data folder, Shared writable directory, Home directory

**Local Development Runtime**:
The non-commercial development boundary used by this workspace. Kiosk requests may use the development device principal without a provisioned device credential, while Admin manager capabilities still require a password-authenticated manager session. It is not evidence that the system is ready for a secured pilot or production deployment; its Traditional Chinese display term is 「本機開發展示環境」.
_Avoid_: Secured pilot, Production runtime, Public deployment

**Shared Infrastructure Degradation**:
The Pilot operating state in which customer ordering remains available with bounded process-local protection while Redis-backed cache and rate-limit coordination are unavailable, but operations requiring a distributed lock are refused. The state must be visible as degraded and trigger operator attention, and its Traditional Chinese display term is 「共享基礎設施降級狀態」.
_Avoid_: Redis optional, Full service outage, Silent fail-open, Lock fallback

**Device-Authenticated Admin Access**:
The sole Admin access boundary issued to a store device that holds a valid Kiosk device credential. It grants the Admin surface its complete scoped management capabilities without a separate password or Manager Mode, while an anonymous browser without the device credential remains unauthorised; its Traditional Chinese display term is 「裝置認證 Admin 存取」.
_Avoid_: Staff Mode, Manager Mode, Anonymous Admin, Unauthenticated Admin, Kiosk customer surface

**Device Verification Boundary**:
The bounded wait in which Admin or Kiosk establishes its device identity before opening its surface. Every attempt has a time limit, and the surface always rests in exactly one of three visible outcomes: verified, service starting — which retries on its own — or device unauthorised, which needs a person. A connection that is accepted and then never answered is a starting service, not an unauthorised device: reporting it as one sends staff to re-provision hardware that was never in question. A control disabled for an attempt is returned when that attempt ends, because a bound that leaves the recovery action dead has not bounded anything; its Traditional Chinese display term is 「裝置驗證邊界」.
_Avoid_: Unbounded wait, Starting service shown as unverified device, Locked retry control, Browser-only timeout

**Admin LLM Debug Access**:
The Admin-only capability for listing configured models and running diagnostic prompts under Device-Authenticated Admin Access. It is distinct from customer-facing AI assistance, which follows the Kiosk request boundary; its Traditional Chinese display term is 「Admin LLM 測試權限」.
_Avoid_: Manager LLM Debug Access, Customer AI permission, Public model test

**Containerized Application Runtime**:
The sole supported execution boundary for development, verification, and single-store pilot operation. Completion and release-readiness evidence must come from this boundary; host-native Python or Conda execution is outside the Project runtime contract, and its Traditional Chinese display term is 「容器化應用執行環境」.
_Avoid_: UI API Python Runtime, Conda runtime, Ambient Python, Dual-runtime acceptance

**Pilot Configuration Authority**:
The one host-external, privately permissioned configuration and secret source used by the Containerized Application Runtime during a Pilot. Repository environment files belong only to development and are never consulted to establish Pilot readiness, and its Traditional Chinese display term is 「試營運設定權威來源」.
_Avoid_: Repository .env, Layered environment fallback, Developer machine defaults, Committed secret

**Text Model Routing Policy**:
The store's persisted choice of how text-model requests use the local and cloud halves of the provider chain: local-first, cloud-first, local-only, or cloud-only. It is one setting governing every text-model caller — voice assistance, emotion extraction, and Admin-side authoring of [[AI Push Copy]] — and local-only is the only value under which no customer utterance leaves the store. Serving push copy is not a caller, because it is looked up rather than generated. It is not a provider name and not a per-caller choice; its Traditional Chinese display term is 「文字模型選路策略」.
_Avoid_: AI provider toggle, Model picker, Per-feature model choice, Streaming-only exception

**Cloud Text Provider**:
NVIDIA NIM, the one external service filling the cloud half of the chain. It is fixed rather than chosen — no persisted setting selects a provider, only whether the [[Text Model Routing Policy]] admits cloud at all — and it is only reached when the policy does, with configuring cloud never implying it can serve. Naming it for a single [[Diagnostic Provider Override]] is not selecting it, because that names nothing that outlives the request; its Traditional Chinese display term is 「雲端文字提供者」.
_Avoid_: Persisted provider field, Provider setting, Gemini, OpenAI-compatible endpoint, Configured-means-working

**Diagnostic Provider Override**:
The provider and model an Admin holding [[Admin LLM Debug Access]] names for one diagnostic prompt. It is never persisted, never consulted by customer traffic, and never changes the [[Text Model Routing Policy]] for any other caller — it exists so that one half of the chain can be exercised in isolation, which is the only way to tell an unready half apart from a policy that never reaches it. It must name a half that exists: an absent or unrecognised provider is refused rather than resolved into the local runtime, because a diagnostic that quietly answers from somewhere else reports the opposite of what happened; its Traditional Chinese display term is 「診斷提供者覆寫」.
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
The currently installed default local emotion-inference runtime and one compatible [[Emotion Model Profile]]. It remains selected until an administrator explicitly selects another installed compatible profile; no runtime failure triggers automatic model switching, and its Traditional Chinese display term is 「R1-Omni 情緒執行環境」.
_Avoid_: Generic text model, Automatic provider fallback, Unvalidated emotion adapter

**Emotion Model Profile**:
An installed emotion adapter and model version that satisfies the project's structured emotion and media-capability contracts and may be selected in Admin. Free-form text models and unvalidated providers are never selectable; its Traditional Chinese display term is 「情緒模型設定檔」.
_Avoid_: Arbitrary model ID, Ollama text model, Provider URL, Automatic fallback target

**Emotion Model Readiness**:
Runtime evidence that the selected [[Emotion Model Profile]] has loaded its model, identifies its adapter and version, and declares the media or audio capabilities required by the requested Admin or Voice flow. A failed handshake pauses new customer emotion captures with an explicit reason without clearing the selected analysis mode; capture resumes when readiness returns, while UI API, ordering, and checkout remain available. Its Traditional Chinese display term is 「情緒模型就緒狀態」.
_Avoid_: Port open, Saved model name, Process alive

**Customer Emotion Analysis Mode**:
The one mutually exclusive store setting that governs customer emotion capture: Off captures nothing, Periodic Ordering captures one bounded media clip after another only after the previous analysis finishes until ordering ends, and Voice Only analyzes only media aligned to a Voice Turn. A non-Off mode remains enabled while Emotion Model Readiness is unavailable, but starts no capture until readiness returns; modes never run together or accumulate concurrent inference work. Its Traditional Chinese display term is 「顧客情緒分析模式」.
_Avoid_: Multiple trigger checkboxes, Continuous full-session recording, Concurrent analysis queue, Automatic mode fallback

**Ordering Emotion Capture Boundary**:
The lifecycle boundary for Periodic Ordering emotion capture. It begins only after the customer enters the menu and ends on Order Confirmation, ordering cancellation, ordering-session inactivity timeout, or Kiosk reset. At the boundary the system starts no new capture, discards media whose capture has not completed, and allows an already submitted inference to finish and record its correlated result without starting another clip; its Traditional Chinese display term is 「點餐情緒擷取邊界」.
_Avoid_: Browser-page lifetime, Full-session recording, Cancelled submitted inference, Post-order capture

**Periodic Emotion Clip Duration**:
The configurable media duration for each Periodic Ordering capture, from two to thirty seconds with a five-second default. It applies only to captures that begin after a setting change and never truncates an observation already in progress; its Traditional Chinese display term is 「週期情緒片段時長」.
_Avoid_: Voice Turn duration, Analysis interval, Mid-capture setting change, Fixed five-second rule

**Emotion Model Observation**:
The authoritative structured result produced by the selected [[Emotion Model Profile]] for one evidence capture. It identifies the adapter and model version, evidence mode and capture identity, transcript presence, one [[Operational Emotion Classification]], facial and vocal evidence summaries when available, description, model-native confidence when supplied, and latency. It never exposes model chain-of-thought, and missing confidence is reported as not provided rather than invented; its Traditional Chinese display term is 「情緒模型觀測」.
_Avoid_: Generic LLM answer, Emotion explanation, Fused model result, Raw model reasoning

**Operational Emotion Classification**:
The normalized emotion and intensity pair accepted by project APIs and persistence. Emotion is exactly Neutral, Happy, Angry, Frustrated, Anxious, Confused, or Undetermined; intensity is exactly Low, Medium, High, or Undetermined. Provider-specific labels and free text must be mapped before acceptance, and anything that cannot be mapped reliably becomes Undetermined while supporting detail remains in the overall description; its Traditional Chinese display term is 「營運情緒分類」.
_Avoid_: Free-form emotion label, Invented intensity, Silent fallback, Provider-specific enum

**Customer Emotion Advisory**:
A staff-facing reference composed from Emotion Model Observations that may help customer service understand an ordering interaction. It never changes voice responses, recommendations, prices, ordering decisions, or any other customer flow automatically; its Traditional Chinese display term is 「顧客情緒參考」.
_Avoid_: Active intervention, Automated personalization, Pricing signal, Customer-facing diagnosis

**Emotion Diagnostic Acceptance Set**:
A fixed, balanced, non-customer collection of labeled audio-only and live-media samples used to verify the selected provider against the non-Undetermined values of [[Operational Emotion Classification]]. It is acceptance evidence rather than training material, and its Traditional Chinese display term is 「情緒診斷驗收集」.
_Avoid_: Customer recording archive, Training corpus, Provider health check, Free-form emotion labels

**Emotion Analysis Record**:
A store-scoped structured result retained for 30 days from Periodic Ordering, Voice Only, or a Live Admin Emotion Test. Its visible and retained analysis fields are time, event, model, emotion, intensity, facial evidence, vocal evidence, and overall description; only opaque record identity and store scope may accompany them for isolation and deletion. An inference submitted but ending in failure still creates one record with Undetermined emotion and intensity, Not Observed facial and vocal evidence, and a safe failure description without internal exception details. Raw image, video, audio, and transcript content are discarded after inference, and the record is permanently deleted when its retention period expires. Emotion and intensity remain separate data fields even when the UI combines them into one cell; its Traditional Chinese display term is 「情緒分析紀錄」.
_Avoid_: Raw media archive, Transcript history, Permanent diagnostic log, Effectiveness evidence, Intervention outcome

**Emotion Legacy Purge**:
The one-time permanent removal, without backup, of pre-P2 emotion intervention modes, rollout and confidence controls, human evaluations, effectiveness evidence, voice-influence records, assistance outcomes, and their UI, APIs, code, and storage. Emotion Model Profiles, Customer Emotion Analysis Mode, Live Admin Emotion Test, and the minimal Emotion Analysis Record remain authoritative; its Traditional Chinese display term is 「情緒舊功能永久清除」.
_Avoid_: Archive, Hidden legacy UI, Retained effectiveness table, Reversible retirement

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
The soft-removal of a [[Store Menu Item]] from the sellable catalog. Retired items are hidden from kiosk and new orders, remain addressable for history and admin recovery, and are distinct from disabled (still listed, temporarily not sold). Only a [[Device-Authenticated Admin Access|device-authenticated Admin]] may retire or restore; its Traditional Chinese display term is 「商品退役」.
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

**Guest Ordering Choice**:
The single customer choice on the initial ordering-mode screen to begin ordering without member identity. Member login and registration screens do not carry a standing 「略過，直接點餐」 action; customers return to the ordering-mode screen before choosing guest entry, and its Traditional Chinese display term is 「訪客點餐選擇」.
_Avoid_: Registration cancellation, Member-flow skip button, Offline menu entry, Separate skip path, Anonymous member

**Guest Ordering Start Failure**:
The recoverable state after the system cannot establish the guest ordering session requested by a Guest Ordering Choice. The customer remains in the entry flow with a visible explanation and retry action; no offline or incomplete menu is opened, and its Traditional Chinese display term is 「訪客點餐啟動失敗」.
_Avoid_: Silent button failure, Automatic offline ordering, Abandoned entry flow, Permanent failure

**Member Login Service Failure**:
A technical failure while checking a customer's phone number. It keeps the customer on the login screen and offers 「重試」 or a return to the initial ordering-mode screen; guest entry is available only through that screen's [[Guest Ordering Choice]]. It is distinct from a successful lookup that confirms the phone number is not registered and must never open registration automatically.
_Avoid_: Member not found, Automatic registration

**Member Registration Service Failure**:
A technical failure after a customer submits registration. It keeps the entered phone number, nickname, and consent state on the registration screen, explains that registration was not completed, and offers 「重試」 or a return to the initial ordering-mode screen. It never exposes a member-flow guest shortcut or silently starts a guest order.
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

**Confirmed Order Value**:
The sum of server-authoritative totals for Orders successfully created by Order Confirmation within a reporting period. It is an accepted-order amount rather than collected revenue and must remain labeled 「已確認訂單金額」 until trustworthy Paid outcomes exist.
_Avoid_: Revenue, Collected sales, Client cart total, Attributed revenue

**Payment Pending**:
The state of a confirmed Order whose payment still requires provider or counter completion. Manual payment remains Payment Pending until an explicit payment result marks it Paid or Failed; its Traditional Chinese display term is 「待付款」.
_Avoid_: Paid, Order confirmation failure, Assumed counter payment

**Pilot Payment Boundary**:
The first closed Pilot ends its automated transaction at Order Confirmation and hands a Payment Pending order to the staffed counter for manual collection. It is real ordering operation but is not evidence of electronic-payment readiness, and its Traditional Chinese display term is 「試營運付款邊界」.
_Avoid_: Payment success, Integrated payment, Demo-only order, Automatic paid state

**Confirmation Outcome Unknown**:
The Kiosk state after submitting Confirm Checkout when transport failure prevents it from knowing whether the Order was created. The Kiosk preserves the Checkout Quote and idempotency key and queries or retries with that same identity until it finds the Order or receives an authoritative rejection; it never treats uncertainty as failure or starts a second confirmation. Its Traditional Chinese display term is 「訂單確認結果未知」.
_Avoid_: Checkout failed, Retry with new key, Duplicate order

## Voice Ordering Language

**Menu-Wide Voice Listening**:
The customer-ordering state in which the Kiosk automatically monitors microphone input from Menu Ready until Order Confirmation, ordering cancellation, ordering-session inactivity timeout, or Kiosk reset, and begins Voice Turns through [[Open Speech Activation]] without a customer pressing a voice control. It is bounded to the active menu rather than the browser-page lifetime, and its Traditional Chinese display term is 「菜單全程語音監聽」.
_Avoid_: Per-turn voice button, Startup-screen listening, Unbounded background listening, Voice Turn

**Open Speech Activation**:
The Voice Turn activation rule that accepts every complete speech segment detected during [[Menu-Wide Voice Listening]] without requiring a wake phrase, confirmation prompt, or button press. Background conversation may therefore create a Voice Turn and must be treated as an explicit accepted product trade-off rather than silently filtered by an undeclared intent rule; its Traditional Chinese display term is 「開放語音觸發」.
_Avoid_: Wake phrase, Keyword activation, Confirmation-before-submit, Intent-gated speech

**Half-Duplex Voice Listening**:
The turn-taking rule that pauses [[Menu-Wide Voice Listening]] as soon as [[Open Speech Activation]] accepts a segment and keeps it paused through transcription, assistant work, synthesis, and audio playback. Listening resumes only after playback completes or fails and a short echo cooldown of no more than 500 milliseconds has elapsed, so the Kiosk cannot hear its own reply or accept an overlapping Voice Turn; its Traditional Chinese display term is 「半雙工語音監聽」.
_Avoid_: Barge-in, Overlapping Voice Turns, Listening during TTS, Discarded customer speech during playback

**Voice Speech Boundary**:
The speech-segmentation rule for [[Open Speech Activation]]: speech shorter than 250 milliseconds is rejected as noise, 1.2 seconds of silence after accepted speech submits the Voice Turn, and one turn may capture for at most 30 seconds. These customer-facing timing bounds remain stable while model thresholds are calibrated separately; its Traditional Chinese display term is 「語音發話邊界」.
_Avoid_: Sound-level threshold, Unlimited utterance, Immediate pause split, Fixed recording window

**Voice Listening Indicator**:
The always-visible Kiosk microphone state shown throughout [[Menu-Wide Voice Listening]], distinguishing listening, processing, playback, and unavailable states without requiring customer interaction. It has no pause or mute action; a customer ends monitoring only by reaching the ordering boundary or cancelling the ordering session, and its Traditional Chinese display term is 「語音監聽指示」.
_Avoid_: Voice activation button, Customer mute control, Browser-only microphone indicator, Hidden listening state

**Voice Listening Unavailable**:
The visible Kiosk degradation state when the required browser voice-activity model, audio worklet, or microphone permission cannot support [[Menu-Wide Voice Listening]]. Voice Turns are disabled for that ordering session without falling back to RMS detection or a manual voice button, while touch ordering remains fully available; its Traditional Chinese display term is 「語音監聽不可用」.
_Avoid_: RMS fallback, Manual voice fallback, Ordering failure, Silent voice disablement

**Fixed Voice Language Policy**:
The Kiosk UI, speech recognition, voice-assistant text, and synthesized speech use Traditional Chinese only. Voice turns do not expose a language selector, detect a response language, or carry an English prompt/voice setting; its Traditional Chinese display term is 「固定語音語言政策」.
_Avoid_: Voice language switching, automatic response-language detection, English voice reply

**Voice Turn**:
A single customer voice interaction with a stable `voice_turn_id` scoped to its store and ordering session. During [[Menu-Wide Voice Listening]], it begins through [[Open Speech Activation]] without a customer pressing a voice control and submits according to the [[Voice Speech Boundary]]. Visible 「立即送出」 and 「取消」 controls remain available as manual recovery paths after a turn begins. Every Voice Turn reaches exactly one visible terminal outcome: completed, cancelled, no recognizable speech, permission unavailable, recording failure, transcription failure, assistant failure, or playback failure. Completion requires text-to-speech to produce playable audio for the assistant reply; retaining generated text after a playback failure is recovery evidence and never converts the turn into success. Whether that audio reached the customer is confirmed by TTS service availability and on-site verification rather than a per-turn playback report, so a recorded completion means speech was produced and delivered rather than heard. Retrying the same `voice_turn_id` resumes or replays that Voice Turn and never creates a second assistant execution, Voice Order Draft, or Voice Emotion Observation request; its Traditional Chinese display term is 「語音回合」.
_Avoid_: Hold-to-talk, Per-turn voice button, Indefinite recording, Voice session

**Voice Media Degradation**:
The fallback boundary that keeps a Voice Turn available with microphone input alone when camera permission, capture, or emotion-video analysis is unavailable. Camera-derived emotion is optional enrichment and must never block recording, transcription, assistant execution, synthesized-speech playback, or ordering. Until the selected [[Emotion Model Profile]] has [[Validated Audio-Only Emotion Capability]], a microphone-only Voice Turn records an explicit skipped emotion outcome rather than invoking audio-only emotion inference; its Traditional Chinese display term is 「語音媒體降級」.
_Avoid_: Camera-required voice, Combined camera-and-microphone failure

**Voice Emotion Observation**:
An asynchronous optional enrichment derived from a completed Voice Turn. It never delays or changes the Voice Turn that produced it; once complete, it may inform a later Voice Turn under the assistance policy or remain operational evidence. Its Traditional Chinese display term is 「語音情緒觀測」.
_Avoid_: Synchronous voice prerequisite, Current-turn emotion gate, Customer emotion diagnosis

**Voice Playback Failure**:
An unsuccessful terminal Voice Turn outcome in which transcription and assistant execution succeeded but text-to-speech produced no playable audio after bounded retry. The kiosk preserves generated text and any Voice Order Draft only as recovery evidence, reports the failure explicitly, and never counts the turn as completed. A browser that cannot play audio that was produced and delivered shows the customer the same explicit failure but does not rewrite the recorded outcome; its Traditional Chinese display term is 「語音播放失敗」.
_Avoid_: Successful degraded turn, Silent playback failure, Discarded recovery text

**Voice Response Wait**:
The customer-perceived interval from the customer's last detected speech to the first perceivable assistant response, whether visible text or audible speech. Its P95 target is at most three seconds and optional enrichment such as camera emotion analysis is outside this critical interval; its Traditional Chinese display term is 「語音回覆等待」.
_Avoid_: Full-response duration, API response-header latency, Emotion-analysis completion time

**Progressive Voice Response**:
A Voice Turn response that displays validated assistant text as soon as it becomes available and begins synthesized speech afterward without withholding the text. Text is the first response surface, but the turn reaches completion only after synthesized speech plays successfully; its Traditional Chinese display term is 「漸進式語音回覆」.
_Avoid_: Processing placeholder, Audio-gated text, Unvalidated JSON fragment

**Voice Dialogue Display Order**:
The Kiosk presentation rule that establishes the customer's message row before showing assistant text for the same Voice Turn. It uses an available partial transcript or a visible transcription-in-progress placeholder until the final transcript replaces it, while synthesized audio remains free to stream without waiting for final transcription display; its Traditional Chinese display term is 「語音對話顯示順序」.
_Avoid_: Assistant-first transcript, Final-transcript audio gate, Late row insertion, Completed-turn-only redraw

**Voice Menu Candidate Set**:
The small request-specific set of menu items selected by names, aliases, and retrieval signals for one Voice Turn. The voice LLM reasons only over this set rather than the full store menu, while the server remains authoritative for item IDs, prices, availability, and proposed order items. When no candidate is sufficiently reliable, the kiosk presents a few similar items for explicit customer selection instead of loading the full menu or guessing an order item; its Traditional Chinese display term is 「語音菜單候選集」.
_Avoid_: Full menu prompt, Unvalidated LLM menu, RAG knowledge result

**Voice Order Draft**:
A non-transactional set of proposed menu items and quantities produced from a Voice Turn. The kiosk displays every confidently matched item in a dedicated confirmation modal, initially unchecked, and displays ambiguous mentions separately with two or three unselected similar items. The customer may adjust quantities, select related recommendations, and choose which draft items to include. No item enters the cart until the customer presses 「確認加入購物車」; only checked items are added, cancellation leaves the cart unchanged, and only one Voice Order Draft may await confirmation before another Voice Turn begins. Its Traditional Chinese display term is 「語音點餐草稿」.
_Avoid_: Voice cart action, Automatic add to cart, Confirmed order

**Voice Interaction Evidence**:
A store-scoped, de-identified individual record retained for 30 days as the single shared source for Admin voice-record review and Daily Optimization Simulation. Every backend-accepted Voice Turn produces one when it reaches a terminal outcome, including completion and STT, assistant, or playback failure; speech rejected locally as noise or cancelled before backend acceptance produces none. After irreversible personal-data masking, it contains observation time, available STT text and LLM answer, voice outcome or safe failure type, retry or correction outcome, and an RAG outcome of hit, miss, or not run. Hit means the assistant used at least one threshold-eligible Published Knowledge result, miss means retrieval ran without such a result, and not run means retrieval never occurred; only miss may support an RAG Knowledge Gap. It may retain opaque knowledge, publication, and index references plus a safe result count, but no similarity scores, retrieved excerpts, or Knowledge Content copies. Only opaque record identity and store scope accompany it; ordinary Admin review sees its safe summary, while full text requires [[Sensitive Voice Evidence Access]]. It contains no raw audio, member or device identity, session identifier, order or payment details, or individual emotion observation; evidence that cannot be safely de-identified is discarded before persistence. It is encrypted at rest, never used as model-training data, and is permanently removed with derived indexes and backups at TTL expiry. Its Traditional Chinese display term is 「語音互動證據」.
_Avoid_: Separate Admin conversation log, Raw transcript with personal data, Voice session history, Customer profile, Order analytics, Training corpus

**Admin Voice Evidence Review**:
The dedicated, read-only top-level Admin surface for finding a store's Voice Interaction Evidence by date, terminal outcome, failure type, and RAG-hit outcome. It requires `voice.evidence.summary`, which is independent of `optimization.summary`; without that permission its navigation item and workbench deep link are absent, while a workbench user may still see aggregate reconciliation. It defaults to today and permits only the current 30-day retention window, using the Voice Turn's observation time and store timezone rather than projection time or server date; a historical day spans local midnight to the next midnight, while today ends at the explicit search cutoff. A date outside retention is shown as expired rather than as zero results. It queries one day at a time through stable server-side cursor pagination, defaults to 50 rows with 25, 50, or 100 available, sorts newest first, and filters terminal outcome, failure type, RAG outcome, and presence of STT or assistant text. Before step-up, each row shows time, terminal outcome, RAG outcome, whether STT and assistant text exist, and retry or correction outcome without any conversation excerpt; it provides no editing, reclassification, ordinary deletion, full-text search, or export. Records expire automatically after 30 days, while any exceptional governance purge is a separate audited process. Resolving the full masked STT text and complete LLM answer requires Sensitive Voice Evidence Access. Daily Operations Diagnostic Workbench reports how many records it found, used, or excluded and may link here with the same store date and filters; browser return preserves the workbench's selected date and latest result instead of embedding a second record browser. Its Traditional Chinese display term is 「語音紀錄」.
_Avoid_: Raw voice archive, Diagnostic report history, Statistics widget, Second evidence store

**Voice Evidence Projection**:
The reliable asynchronous creation of exactly one Voice Interaction Evidence record from each backend-accepted terminal Voice Turn. It never changes or delays the customer-visible Voice Turn outcome; temporary projection failure is retried idempotently, while unresolved lag or failure remains visible to Admin and prevents a missing projection from being reported as proof that no voice interaction occurred. On first release, one bounded backfill applies the same masking and idempotency rules only to still-retained terminal Voice Turns within the evidence-retention window; it never reconstructs older content from session logs, backups, or raw media, and any RAG outcome that cannot be proven becomes not run. Its Traditional Chinese display term is 「語音證據投影」.
_Avoid_: Voice-flow transaction, Best-effort callback, Duplicate evidence, Invisible ingestion failure, Direct cross-module table write

**Voice Evidence Capability**:
The Business Capability Module with sole authority over Voice Interaction Evidence, Voice Evidence Projection, 30-day retention, reconciliation, and metadata queries. Voice Turn supplies durable terminal events, Admin Voice Evidence Review uses its Capability HTTP API, and Optimization Lab consumes its bounded Capability Interface to create Daily Evidence Snapshots; neither caller owns, copies, or directly queries its storage. Its Traditional Chinese display term is 「語音證據能力」.
_Avoid_: Optimization evidence table, Voice Turn transcript API, Shared repository, Duplicate diagnostic evidence

**Voice Evidence Reconciliation**:
The store-day accounting that partitions backend-accepted Voice Turns into still processing, terminal but awaiting projection, projected evidence found, and known permanent projection failure, without overlap. Found evidence is further partitioned into adopted or excluded records with safe exclusion reasons, and only adopted records count toward diagnostic evidence thresholds. Admin states distinguish true zero activity, in-flight turns, projection lag, permanent projection failure, total exclusion, retention expiry, query failure, analyzer unavailability, and permission denial; none may be collapsed into an empty-data message. Its Traditional Chinese display term is 「語音證據核對」.
_Avoid_: Evidence count only, Projection count as Voice Turn count, Overlapping status totals, Hidden exclusions

**Voice Model Warm State**:
The runtime condition in which the configured local voice LLM has been loaded before the kiosk accepts Voice Turns and is kept resident for the configured interval. Model loading belongs to the voice capability's own readiness — one [[Capability Warm-Up State]] — rather than to the first customer's Voice Response Wait or to the readiness of the service as a whole. A Voice Turn arriving before it completes is refused as [[Voice Listening Unavailable]] rather than made to wait for the load; its Traditional Chinese display term is 「語音模型預熱狀態」.
_Avoid_: First-customer warm-up, Permanent GPU assumption, STT warm state, Global startup gate

**Live Admin Emotion Test**:
An isolated Admin diagnostic that records exactly one audiovisual clip for the selected [[Live Emotion Diagnostic Duration]], then analyzes it with the selected [[Emotion Model Profile]] and one [[Live Emotion Diagnostic Prompt]]. It remains available independently of the Customer Emotion Analysis Mode, runs once per explicit test action, discards raw media after inference, and never changes or starts Kiosk customer capture; its Traditional Chinese display term is 「管理端即時情緒測試」.
_Avoid_: Automatic test loop, Production capture, Persisted raw media, Kiosk intervention

**Live Emotion Diagnostic Prompt**:
The editable prompt for one Live Admin Emotion Test, initialized from a server-owned default and discarded after that test. It never changes the prompt used by Kiosk customer analysis and may be restored to its default before execution; its Traditional Chinese display term is 「即時情緒診斷 Prompt」.
_Avoid_: Production emotion prompt, Persisted setting, Customer-analysis override, Prompt history

**Live Emotion Diagnostic Duration**:
The recording duration for one Live Admin Emotion Test, selected from two to thirty seconds with a five-second default. It is independent of [[Periodic Emotion Clip Duration]] and never starts another capture automatically; its Traditional Chinese display term is 「即時情緒診斷時長」.
_Avoid_: Production clip duration, Adaptive speech window, Automatic cadence, Unlimited recording

**Validated Audio-Only Emotion Capability**:
A provider capability declared only after its explicit audio-only inference contract passes controlled comparisons covering the same semantic content with differing prosody and differing semantic content with the same neutral prosody. Before validation, audio-only inference may exist only as an isolated Admin experiment and must not run in Kiosk customer flows; wrapping synthetic audio in a blank video or advertising `audio_only` in a health response does not qualify. Its Traditional Chinese display term is 「已驗證純音訊情緒能力」.
_Avoid_: Assumed Whisper capability, Blank-video wrapper, Port readiness, Experimental result presented as reliable

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

**Passive Recommendation Continuity**:
The customer-facing guarantee that an active Kiosk menu with at least one eligible item always retains a valid passive recommendation, using the latest valid recommendation or a local eligible fallback when a fresh result is unavailable. It may be hidden only while voice assistance, the cart, or payment occupies the customer flow and returns immediately afterward; its Traditional Chinese display term is 「被動推薦連續性」.
_Avoid_: Paused recommendation, Empty recommendation, API-dependent recommendation, Permanent hide after interruption

**New Item Window**:
The dated period during which a menu item counts as new for [[Push Scope]]. An operator ticks the item and sets an end date, after which it stops counting without anyone having to untick it; its Traditional Chinese display term is 「新品檔期」.
_Avoid_: Permanent new flag, Menu import date, Campaign schedule

## RAG Governance Language

**Essential RAG Operations Surface**:
The complete Admin scope for store retrieval: manage Knowledge Items, publish one Retrieval Method, and run an ad hoc RAG call that displays its result and failure. Evaluation programs, test-case governance, readiness evidence, comparison workflows, import history, alerts, and historical configuration management are outside this surface; its Traditional Chinese display term is 「RAG 核心操作介面」.
_Avoid_: RAG Studio, Evaluation console, Readiness workflow, Multi-knowledge-base manager

**RAG Legacy Purge**:
The one-time permanent removal, without backup, of pre-pilot data and artifacts owned only by RAG features excluded from the Essential RAG Operations Surface. Current Knowledge Items, the Published index, the active Retrieval Configuration, and work required to publish them remain authoritative; its Traditional Chinese display term is 「RAG 舊功能永久清除」.
_Avoid_: Archive, Soft delete, Hidden legacy UI, Reversible retirement

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

**Knowledge Change Candidate**:
A reviewable proposed creation or revision of one store's Knowledge Item produced only when a daily diagnosis classifies an RAG Knowledge Gap, reaches Reference Guidance through repeated or reproducible evidence, and passes Offline Optimization Evaluation. The system compares same-store knowledge and recommends either creating a new item or revising one explicitly identified item, with the existing and proposed contents visible for review. An administrator may edit its title, category, content type, or content, but any edit invalidates its acceptance result and requires a new Offline Optimization Evaluation before confirmation is enabled. A revision candidate identifies the compared Knowledge Item revision; if that item changes before confirmation, the candidate is refused as stale and must be regenerated against current knowledge rather than overwriting or automatically merging it. Each store has at most one pending candidate; starting another diagnosis requires explicit abandonment of it, and it otherwise ends on confirmation, abandonment, or expiry with its 30-day source report. It has no retrieval authority of its own; confirmation requires both `rag.write` and `rag.publish` and sends it through the authoritative knowledge save flow, which then reports Indexing until publication actually succeeds. Its Traditional Chinese display term is 「知識變更候選」.
_Avoid_: Draft, Published knowledge, Automatic RAG update, Reference-only copy text

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

## Project Intelligence Language

**Project Core Brain**:
An Admin capability that produces one [[Project Analysis Snapshot]] and answers questions about it from a bounded [[Project Read-Only Evidence Scope]]. Its first release can inspect and explain but cannot edit files, run arbitrary commands, mutate Git, change runtime configuration, or operate business data. Any future document or non-core feature creation is a separately authorized workflow rather than an extension of read access; its Traditional Chinese display term is 「專案核心大腦」.
_Avoid_: Autonomous coding agent, Shell console, Secret scanner, Business-data assistant, Unbounded repository agent

**Project Read-Only Evidence Scope**:
The complete allowlist available to the first Project Core Brain release: Git-tracked source code, tests, documentation and non-secret configuration inside the repository; CodeGraph or equivalent code-architecture facts; Git status and diffs; Docker container and capability-API readiness; and test results produced by an explicit administrator action. `.env` files, secrets, credentials, customer database records, raw media, home-directory content, project-external paths, and arbitrary shell execution are excluded; its Traditional Chinese display term is 「專案唯讀證據範圍」.
_Avoid_: Filesystem-wide scan, Environment dump, Database query console, Implicit test execution, Arbitrary command output

**Project Analysis Snapshot**:
An immutable, administrator-triggered analysis of the current Project Read-Only Evidence Scope. Its retained report records observation time, Git revision, Project Analyst Profile, healthy, warning, and blocked findings, and a source reference for every claim. Only the latest successful report is retained per project; a successful rescan atomically replaces and permanently deletes the previous report, while a failed rescan preserves the previous report marked stale with a safe failure reason. Sanitized model input, CLI event streams, and reasoning are discarded after report creation, and follow-up conversation exists only in the current browser session. Its Traditional Chinese display term is 「專案分析快照」.
_Avoid_: Live project state, Report history, Persisted source bundle, Persisted chat, Uncited model answer

**Project Analyst Sidecar**:
The dedicated non-root Docker service that runs one allowlisted Codex, Claude, or Grok analysis adapter against a sanitized Project Analysis Snapshot and returns the project's common structured result. It is separate from the App and Worker images, receives automation-specific credentials through Docker secrets, has no Docker socket, home-directory, `.env`, database, raw-media, or whole-repository mount, and cannot mutate project or runtime state; its Traditional Chinese display term is 「專案分析 Sidecar」.
_Avoid_: CLI installed in App container, Personal login mount, Docker socket agent, Repository bind mount, Arbitrary command runner

**Project Analyst Profile**:
A server-discovered Codex, Claude, or Grok adapter identity consisting of its pinned CLI version range, selected model, automation credential readiness, non-interactive capability, enforced read-only and tool restrictions, and common JSON Schema conformance. Only ready profiles appear as selectable in Admin. One profile may be configured as the default and explicitly overridden for a run; an unavailable selected profile blocks that analysis with a reason and never triggers automatic profile switching. Its Traditional Chinese display term is 「專案分析器設定檔」.
_Avoid_: CLI path only, Free-form provider name, Personal login readiness, Automatic fallback, Unvalidated JSON output

**Development Host Analyst Bridge**:
A development-only fallback that exposes the same bounded project-analysis contract through compatible host-installed CLIs when the Project Analyst Sidecar is unavailable. It is never a production dependency, never broadens the Project Read-Only Evidence Scope, and cannot be selected automatically after a sidecar failure; its Traditional Chinese display term is 「開發主機分析橋接」.
_Avoid_: Production host daemon, Automatic fallback, User-home scanner, General CLI proxy

**Project Change Proposal**:
A review artifact produced by a separately authorized advanced workflow in one disposable isolated worktree. It contains a patch, bounded change summary, and test results but never modifies the active workspace, commits, switches branches, pushes, or opens a pull request. Applying the patch is an explicit workflow outside the Project Core Brain; rejection or expiry permanently removes the worktree and proposal artifacts. Its Traditional Chinese display term is 「專案變更提案」.
_Avoid_: Direct project edit, Autonomous commit, Automatic patch application, Hidden worktree, Pull request bot

**Non-Core Extension Module**:
A self-contained new module proposed only under `extensions/<name>/`, with its own small interface, configuration contract, error modes, and tests. It does not edit existing files or depend on UI API implementation details, business database tables, Kiosk state, authentication, ordering, payment, migrations, runtime configuration, Docker integration, or R1-Omni internals. New documents from the same proposal workflow live only under `docs/proposals/`; connecting either artifact to a production flow requires a separately authorized core integration. Its Traditional Chinese display term is 「非核心擴充模組」.
_Avoid_: Hidden core edit, UI plug-in by convention, Shared database access, Direct production registration, Cross-module internal import

**Daily Optimization Simulation**:
A manually triggered, non-production experiment that analyzes explicitly selected Voice Interaction Evidence, synthetic fixtures, or a sanitized administrator import and produces a `reference_only` report containing possible Kiosk LLM or prompt adjustments, possible RAG Knowledge Items, offline evaluation results, risks, and evidence. Its output is informational rather than an executable change: it has no apply or publish action and cannot update live settings, create or edit production knowledge, publish an index, change a recommendation or campaign, send a push, generate an applicable project patch, or schedule another run. Its Traditional Chinese display term is 「每日最佳化模擬」.
_Avoid_: Production optimization job, Automatic publishing, Live configuration mutation, Customer-flow experiment, Scheduled retraining

**Optimization Lab Module**:
The isolated module and Docker service that runs Daily Optimization Simulation through a small structured analysis interface. For formal diagnosis it consumes a bounded Daily Evidence Snapshot from the Voice Evidence Capability and never owns, copies, or directly queries voice-evidence storage; synthetic fixtures or sanitized administrator imports remain separate test inputs. It returns a `reference_only` result and has no project-file, Git, Docker, home-directory, raw-media, database-volume, Shell, Web, MCP, or production-write access. It may reuse provider-adapter implementation code with the Project Analyst Sidecar but never shares its container, credentials, data volume, or Project Analysis Snapshot. Its Traditional Chinese display term is 「最佳化實驗室模組」.
_Avoid_: Project Analyst mode, Shared privileged container, Production optimizer, Customer-data coding agent, General LLM gateway

**Daily Review Analyzer Profile**:
A separately administrator-enabled Codex, Claude, or Grok adapter for a reference-only Daily Optimization Simulation or daily operational review. The adapter discovers and exposes only the models and reasoning-effort values supported by its installed analyzer version; Admin explicitly selects one enabled analyzer, one advertised model, and one advertised effort for a run. Each profile defaults to `synthetic_only`; `customer_evidence` requires separate provider-specific administrator authorization, automation-only credentials, disclosed outbound data categories, an accepted provider-retention configuration, and a per-run egress audit. Unsupported or free-form values are rejected, and failure never switches provider, model, effort, or data scope automatically. Its Traditional Chinese display term is 「每日檢視分析器設定檔」.
_Avoid_: Common invented effort scale, Free-form model, Automatic fallback, Hidden default, Multi-provider implicit run

**Analyzer Data Scope**:
The explicit evidence class selected for one Daily Review Analyzer Profile. Formal daily diagnosis defaults to `customer_evidence`, which means the selected date's de-identified Voice Interaction Evidence; a local-only analyzer may process it inside the store without external-data authorization, while an external analyzer requires per-run authorization, visible provider and outbound-category disclosure, accepted provider retention, automation-only credentials, and an egress audit containing analyzer, model, effort, store, evidence identifiers, counts, and time without copied content. `synthetic_only` is a visibly separate test mode, never mixed into a formal diagnosis or silently selected after failure. A formal run may select only an analyzer ready and authorized for real evidence; if none is ready, the run is unavailable with a specific reason and never falls back to synthetic or an external analyzer, while the latest successful report remains visibly historical. Its Traditional Chinese display term is 「分析器資料範圍」.
_Avoid_: Synthetic default, Mixed real-and-synthetic run, Global external-AI consent, Personal OAuth, Implicit external scope upgrade, Unlogged data export, Raw customer data

**Daily Evidence Snapshot**:
The immutable store-scoped input selection for one Daily Optimization Simulation, covering exactly one calendar date within the 30-day evidence-retention window in the store timezone. A formal snapshot includes every adopted Voice Interaction Evidence record in that boundary plus the reconciliation counts and safe exclusions; administrators cannot hand-pick a subset, and an Admin Voice Evidence Review filter never changes it. A prompt may focus analysis on one failure type but the snapshot still carries the complete adopted set and contradictory evidence. A historical date covers local midnight up to the next local midnight; the current date is allowed but is labeled partial with its run-start cutoff time, and the UI names the corresponding UTC interval. Voice Interaction Evidence belongs to the date of its originating Voice Turn observation rather than its later projection time. Evidence identifiers are frozen when the run starts, later interactions never enter the in-flight run, and including them requires an explicit rerun that creates a new snapshot; an expired date is reported as outside retention rather than as an empty snapshot. Its Traditional Chinese display term is 「每日證據快照」.
_Avoid_: Rolling query, Cross-store day, Server-UTC date, Live-updating report, Implicit rerun

**Daily Diagnostic Question**:
A store-scoped, reusable administrator-authored question with a required display name and a required full prompt, selected to analyze one [[Daily Evidence Snapshot]], such as the name 「今日語音診斷」 with the prompt 「診斷今日語音對話」. The full prompt is an actual analyzer instruction and the response must answer it; it is not display-only metadata. Its prompt may direct analysis freely within the fixed Daily Operations Review Surface but never expands that evidence boundary or overrides evidence completeness, offline evaluation, or publication authority; requests for member or order details, raw media, complete logs, arbitrary database access, direct RAG mutation, or other excluded actions are refused. Reading and running questions requires `optimization.summary`, while creating, editing, or deleting the store's question library requires the separate `optimization.manage` permission. Each store receives the example once on first use as an ordinary editable and deletable question; an edit affects future runs only, and deletion never causes automatic recreation. It belongs to a managed question library and is not a message in the browser-session conversation. Deleting it is permanent and prevents future runs, but reports already produced from it retain immutable copies of both fields until their normal 30-day expiry; its Traditional Chinese display term is 「每日診斷問題」.
_Avoid_: Chat message, Ad hoc prompt, Project question, Retrieval Test Case

**Daily Operations Diagnostic Workbench**:
The primary Admin surface for managing Daily Diagnostic Questions, running one against a selected Daily Evidence Snapshot, reviewing its Daily Optimization Reference Report, and confirming an eligible Knowledge Change Candidate. Formal diagnosis defaults to the selected date's real Voice Interaction Evidence; synthetic fixtures are available only in a visibly separate test mode and never mix with real evidence. Before and after a run, the workbench names the store, local date and time boundary and shows records found, used, excluded, and awaiting projection with safe reasons; zero results are an explicit search outcome, and investigation links to Admin Voice Evidence Review. Known projection lag permits only a visibly incomplete observation report: it cannot reach Reference Guidance or create a Knowledge Change Candidate, and a complete result requires an explicit rerun after synchronization. It presents the selected question and assistant response as a dialogue while keeping classifications, evidence counts, risks, and guidance in structured cards; an eligible response ends by asking whether to preview its RAG change. The workbench restores only the store's latest successful diagnosis and any pending candidate after re-entry; it offers no 30-day report-history browser even though older reports remain under their audit retention. A failed run displays its safe error without replacing that latest result, creates no candidate, and never switches analyzer automatically. The configured analyzer, model, reasoning effort, and evidence mode are preselected in a subordinate analysis-settings area but remain visible and changeable before each explicit run. Individual de-identified STT text or complete LLM answers remain behind Sensitive Voice Evidence Access rather than appearing in the ordinary result. Its date selector defaults to the current date in the store timezone; a current-day run is visibly partial and names its cutoff. Project source, Git, test, and container analysis remains a separate advanced Project Core Brain surface; its Traditional Chinese display term is 「營運診斷工作台」.
_Avoid_: Project Core Brain, Unified project-and-customer analyzer, RAG editor, Chat console

**Daily Operations Review Surface**:
The complete six-section evidence interface exposed to a Daily Review Analyzer Profile: run-time API connectivity; accepted voice, recommendation, and campaign clicks plus Confirmed Order Value; voice success and STT, LLM, TTS, retry, or correction outcomes; RAG hits, misses, suspected knowledge gaps, and issue clusters; aggregate emotion distribution and intensity plus de-identified voice-interaction analysis; and classified findings, reference guidance, offline tests, and risks. Database internals, complete system logs, member or order details, raw media, and individual emotion records are outside the interface. Its Traditional Chinese display term is 「每日營運檢視介面」.
_Avoid_: All-database export, Log dump, Customer profile report, Raw evidence bundle, Analyzer-selected scope

**Optimization Finding Classification**:
The mandatory root-cause category assigned before a Daily Optimization Simulation may produce reference guidance: RAG Knowledge Gap for missing or unretrieved facts; Prompt Behavior for response style, format, or policy mismatch; Model Capability for model quality, latency, or stability; Product Pipeline for Kiosk, STT, TTS, transport, or workflow faults; and Insufficient Evidence when attribution is not supportable. Guidance may target only the classified seam, and Insufficient Evidence never produces a change recommendation. Its Traditional Chinese display term is 「最佳化發現分類」.
_Avoid_: Change-first diagnosis, Multi-layer rewrite, Generic AI issue, Forced recommendation

**Optimization Evidence Level**:
The non-probabilistic evidence status of one Optimization Finding Classification. One or two similar records are an Observation Signal that may describe a pattern but cannot produce concrete adjustment guidance. Three or more similar records, or a behavior reproducible with synthetic fixtures, may become Reference Guidance only when the selected evidence set is known complete; projection lag caps every formal result at Observation Signal until an explicit rerun after synchronization. Reports show actual counts and redacted evidence instead of invented confidence percentages; contradictory evidence becomes Insufficient Evidence. Its Traditional Chinese display term is 「最佳化證據層級」.
_Avoid_: Model confidence score, Single-example recommendation, Hidden threshold, Majority guess

**Offline Optimization Evaluation**:
The isolated replay required before concrete Prompt, model, or RAG Reference Guidance may appear in a Daily Optimization Reference Report. Voice candidates must preserve structured JSON, menu-ID allowlisting, no false order-confirmation claim, Traditional Chinese output, and TTS-safe text; RAG candidates must pass answerable queries, unanswerable queries, source correspondence, and non-fabrication checks. A candidate that regresses any existing safety acceptance is rejected. When evaluation cannot run, the report marks the direction Unverified and omits directly reusable settings or knowledge content. Its Traditional Chinese display term is 「離線最佳化評估」.
_Avoid_: Live customer experiment, Same-example self-review, Safety tradeoff, Untested copy-paste setting, Model self-approval

**Daily Optimization Reference Report**:
A store-scoped `reference_only` result retained for 30 days from one Daily Optimization Simulation over one Daily Evidence Snapshot and the fixed Daily Operations Review Surface. It stores analysis time and cutoff, store timezone and selected date, partial-day status, Daily Review Analyzer Profile identity including analyzer version, model, and effort, the six review sections, finding clusters, occurrence counts, Optimization Finding Classification, Optimization Evidence Level, reference guidance, offline test results, risks, and opaque Voice Interaction Evidence identifiers; it never duplicates STT text or LLM answers. Authorized expansion resolves an identifier to its still-live de-identified evidence and creates an access-audit event. Evidence expiry makes the reference unavailable, and report expiry permanently deletes the report and its references. Its Traditional Chinese display term is 「每日最佳化參考報告」.
_Avoid_: Transcript copy, Permanent report, Executable change plan, Unlogged evidence access, Broken-retention duplicate

**Sensitive Voice Evidence Access**:
The separately approved step-up capability required to resolve Voice Interaction Evidence into de-identified STT text and the complete LLM answer. The current Admin release issues no such authorization, so it exposes only metadata and aggregate diagnosis even when evidence is retained; Device-Authenticated Admin Access and `optimization.evidence.read` alone never reveal conversation text. If this capability is introduced later, it requires its own approved verifier, bounded authorization lifetime, and content-free access audit. Its Traditional Chinese display term is 「敏感語音證據存取」.
_Avoid_: Unimplemented manager-password prompt, Device access as step-up, Report-level transcript exposure, Permanent unlock, Transcript in audit log, Cross-store lookup

**Production Optimization Loop**:
A future, separately authorized capability that may evaluate and release bounded Kiosk LLM or RAG changes from daily operational evidence. It is not part of the current Project Core Brain or Daily Optimization Simulation and has no production authority until its data governance, acceptance gates, rollback, release ownership, and emotion-evidence policy receive explicit decisions. Its Traditional Chinese display term is 「生產最佳化迴路」.
_Avoid_: Current feature, Implicit future permission, Core Brain write mode, Ungated self-improvement

## Operations Reporting Language

**Accepted Engagement Click**:
A unique, server-accepted customer intent counted for the Admin operational overview: starting one Voice Turn, activating the primary action of an AI recommendation, or activating a Campaign call to action. Duplicate delivery, impressions, automatic rotation, refresh, close, and rejected repeated input are excluded; its Traditional Chinese display term is 「有效互動點擊」.
_Avoid_: DOM click, Impression, Retry count, Button press while busy

**API Connectivity Diagnosis**:
An Admin diagnostic that verifies each configured capability API can return its minimum health contract, then reports service name, connection status, latency, observation time, and a concise failure reason. It may verify required model presence or declared media capability but does not judge business data quality, retrieval quality, commercial impact, logs, or historical event samples; its Traditional Chinese display term is 「API 連線診斷」.
_Avoid_: Port-open check, Business readiness dashboard, Log explorer, Data-quality report
