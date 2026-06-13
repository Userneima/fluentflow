# FluentFlow Account And Logged-In User Access Model

## Status

This is a working discussion draft.

It records the current product direction for registration, login, logged-in user behavior, and the boundary between guest trial users, normal accounts, and administrators.

It is not yet an implementation plan. After the direction is accepted, implementation should be split into smaller phases.

## Context

FluentFlow now has a public domain and a working guest trial path.

The product has three different audiences:

- Portfolio visitors who arrive from a resume, portfolio, or shared link.
- Serious evaluators or early users who want to process more than one small trial.
- The maintainer/admin who needs to protect compute cost, storage, and public reliability.

The guest trial solves the first audience:

- No login wall.
- Real transcription and note generation.
- Strict one-file trial limits.
- Temporary same-browser result recovery.

The account system should solve the second and third audiences:

- Let serious users keep history across sessions and devices.
- Let the maintainer selectively grant more usage.
- Avoid turning the product into an uncontrolled public SaaS too early.

## Current Implementation Baseline

Current backend support already includes:

- Account auth mode through `FLUENTFLOW_AUTH_MODE=accounts`.
- `POST /auth/register`.
- `POST /auth/login`.
- `POST /auth/logout`.
- Session cookie named `fluentflow_session`.
- First registered user becomes admin.
- After bootstrap, registration is blocked unless signups are explicitly enabled.
- Job scope changes from browser device `client_id` to `user:{id}` when logged in.
- Logged-in users can retrieve task history from the backend job store.

Current frontend support already includes:

- Login/register form when account auth is required.
- First-admin registration flow.
- Normal account login.
- Logout.
- Guest mode bypass when guest trial is enabled and user is unauthenticated.

Important current gaps:

- No email verification.
- No password reset.
- No invite code.
- No account approval workflow.
- No user management screen.
- No role/balance-based quotas beyond existing environment-level limits.
- No per-user display of remaining quota.
- No migration path from guest result to a newly created account.
- No paid quota/recharge model.
- No account balance, quota ledger, payment provider, purchase table, or entitlement sync.

These gaps matter because public self-registration without quota visibility, abuse controls, or user management creates operational debt immediately. They matter even more if the product later introduces recharge-based usage, because account identity becomes the source of balance, entitlement, and support history.

## Core Product Judgment

The account system should be designed as the future entitlement layer.

That changes the earlier judgment. If FluentFlow will later add paid functionality, open registration becomes more reasonable, because accounts are not only an access-control tool. They are the user's workspace, quota wallet, and future billing identity.

For this product stage, the strongest access model is:

1. Let everyone enter as a guest.
2. Let users create a free account when they want continuity.
3. Give every new registered account a limited free starter quota.
4. Keep global server limits above all account limits.
5. Let users recharge after the free quota is used.
6. Keep admin controls simple and explicit.

This protects the portfolio experience while preparing for paid conversion.

The wrong model would be:

- User lands on the site.
- User sees "register now" as the primary action.
- Anyone can create unlimited accounts.
- Quotas are hidden or unclear.
- The maintainer has no quick way to disable, inspect, or limit accounts.
- Later payment logic has to be bolted onto ad hoc user limits.

That model would increase risk and make future monetization messier.

The better model is:

```text
Guest = immediate real trial.
Registered account = saved history + free starter quota + quota balance.
Recharged account = same product, more available processing quota.
Admin = operations and exception handling.
```

## Account Purpose

An account should not be required to understand FluentFlow.

An account should exist for users who need continuity:

- More than one trial.
- Longer videos.
- Cross-device access.
- Saved task history.
- Re-download of previous results.
- Edited transcript persistence.
- Optional Feishu export if enabled.

The product message should be:

```text
访客可以立即试用。
登录账号用于保存历史、处理更多材料，以及跨设备继续编辑。
```

Not:

```text
请先注册，否则不能使用。
```

## Recommended Access Structure

### Visitor

Visitor means unauthenticated user.

Default behavior:

- Can enter the product.
- Can run one real guest trial within guest limits.
- Can download guest result artifacts.
- Cannot access long-term history.
- Cannot use batch upload.
- Cannot use Feishu export.
- Cannot save edited transcript to long-term account history.
- Cannot change advanced provider or credential settings.

The visitor path should prove product value quickly.

### Registered User

Registered user means a logged-in non-admin account. In the near term this means an account with a free starter quota. Later it can hold a rechargeable usage balance.

Default behavior:

- Can upload more than guest.
- Can access task history across sessions and devices.
- Can open previous results.
- Can download artifacts.
- Can edit transcripts and preserve edits.
- Can regenerate notes if quota permits.
- Can cancel own queued/running tasks.
- Can use Feishu export only if the deployment enables it for normal users.

The registered user path should feel like a real working tool, not just a larger demo.

### Recharged User

Recharged user means a registered account with positive paid usage balance.

This does not need to be implemented now, but the account model should leave room for it.

Likely recharge benefits:

- More available processing units.
- Larger total processing allowance before the next recharge.
- Ability to continue processing after the free starter quota is exhausted.
- More active or queued tasks.
- Longer history retention.
- Longer artifact retention.
- Priority queue or faster processing when capacity exists.
- Batch upload.
- Feishu export or integrations.
- More note-generation/regeneration quota.

Recharge status should not mean "no limits." It should mean "the account has enough balance to pay for metered usage." File size, media duration, active jobs, queue length, and global capacity limits should still exist because they protect reliability, not only cost.

### Admin

Admin means maintainer account.

Default behavior:

- Same product capabilities as registered user.
- Can inspect system health.
- Can eventually manage users, quotas, and access.
- Should not be subject to the same limits when doing maintenance, testing, or recovery, but admin unlimited usage should still be explicit and observable.

Admin should not be the design center of the daily UI. Admin features can live in a small protected operations surface.

## Registration Strategy

### Target: Open Registration With Hard Free Quotas

Open registration can be acceptable if it is not equivalent to unlimited usage.

Recommended account acquisition path:

1. Visitor completes or explores guest trial.
2. Product shows a small account prompt.
3. Visitor creates a free account.
4. The guest session may remain temporary at first; later it can be claimable into the account.
5. User logs in and gets a starter balance and account-scoped limits.

This fits the current public promotion stage because:

- Resume visitors can still try immediately.
- Serious users have a low-friction path forward.
- The product starts building a user base for future paid conversion.
- Cost exposure is bounded by per-account, per-IP, and global limits.
- The account model can later map cleanly to recharge and metered usage.

This does require a stronger quota and abuse boundary than invite-only accounts.

Minimum safety requirements for open free registration:

- Hard per-account quotas.
- Global queue and cost limits.
- IP/rate limits on registration and login.
- Admin ability to suspend users, or at minimum a documented manual database operation.
- Clear quota copy in the UI.
- No unlimited free batch upload.

Recommended rollout order:

1. Maintainer-created accounts for first real users.
2. Invite or quiet signup if the account UX is stable.
3. Open registration only after quota display, cost observation, usage ledger, and suspension exist.

Open registration is the target product direction, not the first technical step.

### Later: Paid Self-Serve Accounts

Paid self-serve accounts become appropriate when these are available:

- Payment provider integration.
- Purchase order table.
- Recharge balance table.
- Usage ledger.
- Entitlement calculation from role, balance, and safety limits.
- Webhook handling.
- Failed-payment or unpaid-order behavior.
- Email receipts or provider-hosted billing portal.
- Password reset.
- Email verification or at least reliable email ownership for billing support.
- Admin user list.
- User disable/suspend action.
- Abuse monitoring.
- Clear terms around storage retention.

Do not implement payments before starter balance, account limits, and usage metering are solid. Payment does not fix quota architecture; it depends on it.

## Registration Entry Points

Registration should not be the first screen.

Recommended placements:

- After a guest task completes.
- When a guest tries to upload a second file.
- When a guest clicks history, Feishu export, batch upload, or longer processing.
- In a quiet top-right account area.
- In a small "保存历史" or "继续使用" prompt.

Avoid heavy modal interruption during the first trial.

Good prompt:

```text
想继续处理更多文件？
创建账号后可以保存历史、跨设备查看结果，并获得基础处理额度。
```

Less good:

```text
注册账号解锁全部功能。
```

The second version sounds like a generic SaaS wall and weakens the portfolio demo.

If recharge is introduced later, still avoid making the first account prompt feel like a checkout page.

Better:

```text
免费账号可保存历史并获得基础额度。
基础额度用完后，后续可充值继续按量使用。
```

## Login Strategy

Login should be useful but not loud.

Recommended behavior:

- Logged-out visitors enter guest mode automatically.
- A "登录" action exists in the top-right or side nav.
- If a visitor attempts an account-only action, show a contextual login prompt.
- After login, return the user to the action they intended if possible.

Login form should support:

- Email.
- Password.
- Clear error for wrong credentials.
- Clear copy when registration is not open.

Login form should not expose:

- Admin language.
- Internal terms like `auth_mode`, `session`, `client_id`.
- Technical quota names.

## Guest To Account Transition

This is important for user experience.

When a guest has a completed result and then logs in or gets an account, there are two possible designs.

### Option A: Guest Result Remains Temporary

The guest result stays as a temporary guest result and is not attached to the account.

Pros:

- Simple.
- Avoids security edge cases.
- Avoids needing a migration endpoint.

Cons:

- User may feel punished after registering.
- The result they just produced does not appear in account history.

This is acceptable for the current launch if the UI clearly allows downloads.

### Option B: Claim Guest Result After Login

After login, the product offers:

```text
是否把刚刚的试用结果保存到你的账号历史？
```

If accepted, backend moves or copies the job from `guest_{token}` scope to `user:{id}` scope.

Pros:

- Strong continuity.
- Feels natural.
- Makes account creation more valuable.

Cons:

- Needs careful token validation.
- Needs a one-time claim endpoint.
- Needs handling if the guest result expired.

This is the better medium-term design.

### Recommendation

For the next account phase, start with Option A if implementation speed matters.

Then add Option B once the basic logged-in experience is stable.

Do not block account work on guest-result claiming. It is valuable, but not foundational.

## Logged-In User Quotas

Logged-in users should have more continuity than guests, but not unlimited usage.

Initial recommended registered-account limits:

- Active jobs per user: 1.
- Waiting queue tasks per user: 2 or 3.
- Starter balance: limited processing units.
- Paid balance: purchased processing units.
- Single upload size: 500 MB to 1 GB.
- Media duration: 60 to 120 minutes.
- History retention: latest 20 tasks.
- Artifact retention: 30 days.

These numbers should be conservative launch defaults. They are also the foundation for later recharge behavior.

Possible later balance and safety limits:

| Capability | Starter account | Recharged account candidate |
| --- | --- | --- |
| Active jobs | 1 | 2-3 |
| Waiting jobs | 2-3 | 10 |
| Processing balance | one-time starter units | purchased units |
| Single file size | 500 MB-1 GB | 2-5 GB |
| Media duration | 60-120 min | 4-8 hours |
| History retention | latest 20 | 100+ or longer time window |
| Artifact retention | 30 days | 90 days or more |
| Batch upload | off or tiny | on |
| Feishu export | off or limited | on |
| Priority queue | no | possible |

Do not promise these paid limits before measuring actual Azure and LLM cost.

The current deployment already has environment-level values close to this:

- `FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT`
- `FLUENTFLOW_MAX_ACTIVE_JOBS_GLOBAL`
- `FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT`
- `FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT`
- `FLUENTFLOW_HISTORY_RETENTION_PER_CLIENT`
- `FLUENTFLOW_ARTIFACT_RETENTION_DAYS`

What is missing is user-facing clarity and per-role customization.

Future quota logic should avoid hardcoding "free" and "paid" directly in request handlers. It should calculate an entitlement profile and balance state from the account:

```text
account -> role + quota balance + safety limits -> admission decision
```

This keeps future payment integration from becoming scattered conditionals.

## Future Payment Model: Metered Recharge

The desired payment model is pay-as-you-go:

```text
registered account receives free starter balance
-> each successful processing task consumes measured balance
-> when balance is insufficient, user recharges
-> recharge adds balance
```

This is different from a subscription plan. The user should feel:

```text
我处理了多少，就为多少付费。
```

### Recommended User-Facing Unit

Do not use raw media minutes as the whole paid unit.

It is tempting because minutes are easy to understand, but it is not accurate enough for a product that claims pay-as-you-go.

The better first user-facing unit is:

```text
processing units
```

Processing units should be shown as a simple balance, but calculated from measurable resource usage behind the scenes.

Recommended first formula:

```text
processing units
= transcription units
+ AI note units
+ optional regeneration units
```

Where:

- Transcription units are mainly based on audio/video duration.
- AI note units are mainly based on transcript length, LLM input tokens, and LLM output tokens.
- Regeneration units are charged when the user asks the model to generate again.

This keeps the product honest:

- A 60-minute quiet meeting should not cost the same as a 60-minute dense lecture if the LLM work is very different.
- A user who repeatedly regenerates notes should pay for the extra AI calls.
- If Azure STT is currently covered by a free allowance, the model can still record STT usage without pretending it is the main paid cost.

Why not expose tokens directly:

- It is easy for users to understand.
- Token accounting is too technical.
- Token counts are hard to predict before the task completes.
- Users care about "how much balance this task uses", not model internals.

So the UI should show estimated and final processing-unit consumption, with a simple breakdown:

```text
预计消耗：约 38 处理额度
转录：约 20
AI 笔记：约 18
```

Do not price by uploaded file size. File size affects upload/storage risk, but it does not reliably represent STT or LLM cost. A highly compressed 2-hour lecture can be small but expensive to process; a large silent video can be large but cheap to summarize.

Do not price by wall-clock processing time. Queue waiting time and provider latency are not user value and should not be charged.

### Internal Cost Reality

Processing units are a product abstraction. They should be grounded in internal cost evidence, not guessed from duration alone.

Current and likely cost drivers:

- STT cost: usually tied to audio duration. Azure Speech may have a free monthly allowance, but paid tiers are still based on transcribed audio time. This means media duration is a strong STT-cost proxy.
- LLM note generation cost: tied to transcript tokens and generated-note tokens. This is currently the more visible paid cost if DeepSeek is the active note provider.
- Storage cost: tied to source files, generated artifacts, retention days, and cleanup discipline. It is likely smaller early, but it becomes real at scale.
- Bandwidth cost: tied to upload/download volume. It is usually secondary early, but large video files can create operational pressure.
- ECS/server cost: mostly fixed monthly cost at the current scale. It becomes a step cost when capacity requires a larger machine or more workers.
- Retry/failure cost: failed STT, repeated LLM generation, and user-triggered regeneration can multiply real cost if not metered or refunded carefully.

Therefore the product should meter both:

```text
user-facing balance: processing units
internal ledger: duration, transcript chars/tokens, LLM input tokens, LLM output tokens, provider, retries, storage
```

### Starter Balance

New registered users should receive a limited free starter balance.

Recommended starting shape:

- Guest: one real trial task with strict limits.
- Registered account: one-time starter processing-unit balance.
- Recharged account: paid balance.

The starter balance should probably be one-time rather than a generous daily reset. A daily reset is easier to abuse by creating multiple accounts, and it weakens the later recharge behavior.

### Consumption Rule

For the first implementation, charge balance from measurable usage, not only media duration.

Recommended default:

```text
transcription units = ceil(media_duration_minutes * transcription_rate)
AI note units = ceil((llm_input_tokens + weighted_output_tokens) / token_unit_size)
total units = transcription units + AI note units + regeneration units
```

Included in the first normal task charge:

- Audio extraction.
- STT.
- Default note generation.
- Standard downloads.

Possible future add-ons:

- Regenerating notes consumes additional balance.
- Very long retention consumes storage balance or requires manual cleanup.
- Feishu export remains free or feature-gated until real demand appears.

### Reservation, Final Charge, And Refund

Before accepting a task, the system should estimate required processing units.

Flow:

1. User selects/uploads a file.
2. Backend reads or estimates media duration.
3. Backend estimates transcription units and rough AI note units.
4. Backend checks whether account balance is enough.
5. Backend reserves estimated balance.
6. Task enters queue.
7. STT completes and produces transcript length.
8. LLM completes and returns token usage if available.
9. Backend calculates final processing-unit consumption.
10. Backend finalizes charge and releases unused reservation.

This creates two user-facing numbers:

```text
estimated units before processing
final charged units after completion
```

The UI should not pretend the estimate is exact. Use wording like:

```text
预计消耗约 38 处理额度，完成后按实际消耗结算。
```

#### Overage Policy

Because AI note token usage is not fully known before the task finishes, the system needs an overage rule.

Recommended beta policy:

- Reserve a conservative estimate before starting.
- Allow small overage up to a fixed buffer, such as 10%-20% above the reservation.
- If final usage is below reservation, release the unused balance.
- If final usage exceeds reservation plus buffer, cap the charge at the reserved amount plus buffer during beta and record the loss in the cost ledger.
- Do not let user balance silently go negative for normal task completion.

This favors trust over perfect cost recovery while the pricing model is still being calibrated.

Later, once estimates are accurate, the system can require more upfront balance or ask the user to confirm when a task may exceed estimate.

#### Refund Policy

Refund rules should be explicit.

Recommended default:

- Internal system failure before expensive processing starts: full reservation refund.
- Queue cancellation before STT starts: full reservation refund.
- Cancellation after STT starts: refund unused AI note portion, do not refund already-started transcription portion.
- STT succeeds but note generation fails: charge transcription units, refund AI note units.
- LLM provider failure before note output is produced: refund AI note units.
- User-triggered regeneration: charge additional AI note units.
- Bad user input, unsupported media, or file validation failure before processing: no charge or full refund.
- Duplicate click or accidental repeated submit caused by frontend/backend bug: refund duplicate charge.

The product should expose a simple explanation, not the whole policy table:

```text
系统处理失败会自动退回未消耗额度。
用户主动重新生成会消耗额外额度。
```

This avoids accepting work that the account cannot pay for, and it prevents balance races when users start several tasks at once.

### Pricing Should Be Based On Observed Cost

Do not set final public prices until enough internal ledger data exists.

Minimum data to collect before final pricing:

- Average media minutes per task.
- Average transcript characters per media minute.
- Average LLM input tokens per task.
- Average LLM output tokens per task.
- Average DeepSeek cost per processing unit.
- Azure Speech billable usage after free allowance.
- Average failure/retry rate.
- Storage retained per completed task.

Until then, any price is only a provisional beta price.

### Early Pricing Floor

The early recharge price should be low enough to reduce purchase friction, but it must not be cost-price or loss-making.

Default principle:

```text
low markup, no loss
```

This means the first public price should cover:

- DeepSeek token cost.
- Azure Speech usage after free allowance is exhausted.
- Payment provider fee.
- Failed task refunds.
- Free starter balance.
- Reasonable retry overhead.
- Storage and bandwidth overhead.
- A small operating buffer.

Recommended launch target:

```text
minimum gross margin: 30%-50%
preferred early gross margin: 50%-70%
```

Do not aim for maximum margin before value and retention are proven. The first goal is to validate that users are willing to pay for continued usage. But do not use a price that depends on Azure staying free or on DeepSeek costs remaining unusually low.

Pricing formula:

```text
unit sale price = average unit cost / (1 - target gross margin)
```

Example:

```text
average cost per processing unit = 0.02 RMB
target gross margin = 50%
unit sale price = 0.02 / (1 - 0.50) = 0.04 RMB
```

This keeps early pricing explainable:

```text
充值买处理额度。
额度按转录和 AI 笔记的实际消耗扣减。
当前价格按低利润试运行设计，至少不亏损。
```

The product should avoid claiming a permanent cheap price. Use beta wording:

```text
试运行价格
```

This leaves room to adjust after real cost data arrives.

## Payment Provider Boundary

If payment is added later, use a provider-hosted checkout or payment page rather than building payment collection UI from scratch.

Likely provider candidates:

- Stripe, if target users can pay internationally and the account setup is viable.
- Lemon Squeezy or Paddle-like merchant-of-record services, if tax and international payment handling matters.
- Local China payment options only if the user base is clearly domestic and the operational path is known.

Provider choice is a separate decision. Do not encode provider-specific concepts into the product model yet.

### Recharge Entry And QR Payment Reality

The recharge flow needs a clearer distinction between three different payment patterns:

```text
personal/static collection QR
merchant payment API generated QR or checkout
third-party hosted checkout or payment aggregator
```

They look similar to the user because all may end with scanning a QR code. They are not equivalent operationally.

#### Personal Or Static Collection QR

This means the maintainer uploads a personal WeChat Pay or Alipay collection QR code and asks users to scan it.

This is acceptable only as a very small closed-beta manual workflow.

Advantages:

- Fastest to start.
- No payment API integration.
- No merchant-account setup before validating willingness to pay.

Problems:

- The product cannot reliably know who paid.
- The product cannot reliably know which order the payment belongs to.
- The product cannot automatically confirm amount, status, refund, or reversal.
- Users may pay the wrong amount.
- Admin must manually check payment records and manually add balance.
- Public self-serve recharge becomes fragile and hard to support.
- It does not create a reliable accounting trail for future paid usage.

Therefore, a static personal collection QR should not be treated as the product's recharge system.

If used temporarily, the product should call it manual recharge:

```text
用户联系管理员 -> 管理员提供收款方式 -> 用户付款 -> 管理员确认到账 -> 管理员手动加额度
```

The app may show an admin-only manual adjustment tool, but it should not automatically credit balance from a static personal QR.

#### Merchant-Generated QR Or Hosted Checkout

This is how normal websites generate "enter amount -> scan QR -> balance arrives" flows.

The product does not generate money-receiving QR codes by itself. It creates an internal order, calls a payment provider, and receives a provider-specific payment URL or checkout session.

Typical flow:

```text
1. User chooses a recharge amount or processing-unit package.
2. Backend creates purchase_order with status=pending.
3. Backend calls provider with order id, amount, description, callback URL, and return URL.
4. Provider returns a payment URL, checkout session, or QR payload.
5. Frontend displays the provider checkout or QR code.
6. User pays in WeChat/Alipay/card/etc.
7. Provider sends an asynchronous payment notification to the backend.
8. Backend verifies provider signature and order amount.
9. Backend marks purchase_order as paid.
10. Backend appends a recharge row to balance_transactions.
11. User balance updates.
```

This is the first design that can support true self-serve recharge.

Important: payment confirmation must come from a verified provider callback or provider order query, not from the frontend returning to the success page. A return page means the user came back; it does not by itself prove that the money settled.

Examples of provider mechanics:

- WeChat Pay Native payment: the merchant backend calls the Native order API, WeChat returns a `code_url`, and the merchant turns that into a QR code. WeChat later sends an asynchronous payment notification. The official WeChat Pay document also notes that `code_url` has a limited validity window.
- Alipay computer website payment or mobile website payment: the merchant backend creates an order and directs the user to Alipay's cashier/payment flow. For QR-like desktop payment, the user may scan with the Alipay app from the cashier experience; the merchant still relies on provider confirmation.
- Alipay face-to-face payment can also generate QR-style payment experiences, but it is primarily a merchant collection product and should be evaluated against the actual account type and scenario.

The practical requirement is usually a real merchant account, application credentials, callback domain, signature verification, and settlement/reconciliation access. This is a business and operations setup, not only a frontend feature.

#### Third-Party Aggregator Or Merchant-Of-Record

A third-party hosted checkout or aggregator can reduce payment integration work, but it still needs to meet basic product requirements:

- Creates an order before payment.
- Sends signed webhooks or verifiable payment events.
- Supports refunds or at least clear failure handling.
- Provides transaction IDs and downloadable records.
- Allows amount and currency to be tied to the purchase order.
- Has acceptable fees, settlement cycle, and account requirements.

Do not use an unofficial "personal QR auto-detection" service as the payment foundation. It may appear to solve the engineering problem, but it usually creates reliability, compliance, and support risk.

### Recommended Recharge Rollout

The safest rollout should be staged.

#### Stage 0: No Public Recharge

Keep the current product focused on guest trial, account quota, and cost observation.

Do not expose a recharge button until:

- Balance ledger exists.
- Usage ledger exists.
- Admin can inspect user balances.
- Shadow billing has enough real tasks.
- Public price and package shape are not pure guesses.

#### Stage 1: Manual Admin Recharge For Known Users

This is the recommended first paid test.

Flow:

```text
User asks for more quota
-> admin shares payment method outside the app
-> user pays
-> admin confirms payment manually
-> admin adds quota with an admin_adjustment or manual_recharge transaction
```

Required product support:

- Admin user list.
- Admin balance adjustment form.
- Required reason field.
- Optional external payment note/reference.
- Append-only balance ledger row.

This stage validates:

- Whether users are willing to pay.
- Whether processing-unit pricing feels understandable.
- Whether balance deduction feels fair.
- Whether support questions appear before automation.

It should be labeled internally as beta/manual. It is not the final payment system.

#### Stage 2: In-App Purchase Order With Manual Confirmation

This is a bridge stage if the product needs a better user experience before payment API integration.

Flow:

```text
User selects recharge amount in app
-> backend creates purchase_order=pending
-> app shows order number, amount, and manual payment instructions
-> user pays externally
-> admin confirms order
-> backend credits balance
```

This is better than a loose QR code because the payment is tied to an internal order. It still requires manual admin confirmation.

Use this only if Stage 1 creates too much admin friction but full provider integration is not ready.

#### Stage 3: Automated Provider Checkout

This is the first real self-serve recharge stage.

Flow:

```text
User selects amount/package
-> backend creates purchase_order
-> provider checkout or QR is created
-> provider confirms payment by webhook/order query
-> backend credits balance automatically
```

Minimum implementation requirements:

- `purchase_orders` table.
- Provider abstraction interface.
- Signed webhook verification.
- Idempotent payment confirmation.
- Amount verification.
- Timeout and unpaid-order cleanup.
- Refund/reversal handling.
- Balance ledger integration.
- User-facing pending/paid/failed states.

Do not credit balance from frontend-only success callbacks.

### Recharge Package Shape

For the first public recharge UI, do not start with a free-form amount input.

Preset packages are safer:

```text
¥9.9  -> small trial top-up
¥19.9 -> normal light-use top-up
¥49   -> heavier early-user top-up
```

Reasons:

- Easier to understand.
- Easier to test pricing.
- Fewer tiny payments lost to provider fees.
- Easier support and refund handling.
- Cleaner ledger and invoice/receipt records.

Free-form amount can be added later for power users or admin-generated links.

The package should show:

```text
充值金额
获得处理额度
预计可处理的大致视频长度范围
按实际消耗扣减，未用完额度保留
```

Do not promise exact minutes from a package. The actual consumption also depends on transcript density, AI note length, and regeneration.

### What The Recharge Page Should Say

The recharge page should be short and operational:

```text
充值处理额度
额度用于音视频转录、AI 笔记生成和重新生成。
任务开始前会预估并冻结额度，完成后按实际消耗结算，多余额度自动退回。
系统处理失败会退回未消耗额度。
```

For manual beta recharge:

```text
当前为人工充值试运行。付款后由管理员确认到账并添加额度，通常不会立即到账。
```

For automated provider recharge:

```text
支付完成后额度会自动到账。如页面未及时更新，可稍后刷新；系统会以支付平台确认结果为准。
```

### Product Decision For FluentFlow

Do not build public self-serve recharge around uploaded personal WeChat/Alipay collection codes.

Recommended path:

```text
shadow billing
-> admin manual recharge for known users
-> in-app purchase order with manual confirmation if needed
-> automated provider checkout only after pricing and ledger are proven
```

This keeps the product honest:

- Manual collection can validate demand.
- Purchase orders create an accounting trail.
- Provider checkout creates real automation.
- Balance ledger remains provider-agnostic.

Internal product model should stay generic:

- `quota_balance_units`
- `reserved_quota_units`
- `free_starter_grant_units`
- `usage_ledger`
- `balance_transactions`
- `purchase_orders`
- `provider_customer_id`
- `provider_payment_id`
- `provider_checkout_id`
- `payment_status`
- `refunded_units`
- `admin_adjustment_reason`

Provider webhooks should only confirm purchases and add balance. Request handlers should only read account balance, reserved balance, safety limits, and admin state.

## Balance Ledger

Do not treat account balance as only a mutable number.

The account may store a cached balance for speed, but the source of truth should be an append-only balance ledger.

Recommended transaction types:

- `starter_grant`
- `recharge`
- `reserve`
- `release_reservation`
- `finalize_charge`
- `refund`
- `admin_adjustment`
- `expired_grant`
- `payment_reversal`

Each ledger row should include:

- Account id.
- Related task id if any.
- Related purchase order id if any.
- Transaction type.
- Unit delta.
- Balance after transaction.
- Rate card version.
- Human-readable reason.
- Provider reference if payment-related.
- Created timestamp.

The cached account balance should be recomputable from ledger rows. This matters for support, refund disputes, and future migrations.

## Balance Expiration

Different balance sources should have different expiration rules.

Recommended default:

- Free starter balance: expires after 30 days.
- Paid recharge balance: does not expire during beta, unless payment provider or local law requires a different rule.
- Admin-granted promotional balance: may expire, but the grant should record its expiry date.

The UI should distinguish:

```text
赠送额度
充值额度
```

Do not silently expire paid balance. If paid balance ever expires, the product must clearly disclose it before purchase.

## Rate Card Versioning

Processing-unit formulas and prices will change.

Every estimate, reservation, final charge, refund, and recharge should record the `rate_card_version` used at that time.

This allows the product to answer:

```text
为什么以前类似任务扣 20 点，现在扣 35 点？
```

Recommended rule:

- A task uses the active rate card at reservation time.
- Final charge uses the same rate card as reservation.
- New pricing only affects new tasks.
- Historical ledger rows should never be recalculated in place.

## Payment Disputes And Reversals

Payment confirmation should be conservative.

Recommended default:

- Only confirmed provider payment events add paid balance.
- Pending or unpaid orders do not add balance.
- If a payment is refunded or reversed, add a negative `payment_reversal` ledger entry.
- If reversal makes balance negative, prevent new paid tasks until the balance is non-negative.
- Admin can freeze or suspend the account while investigating abuse.
- Do not delete user history as the first response to payment issues; block new processing first.

This prevents a user from recharging, consuming balance, and then reversing payment without any operational control.

## Cost Model Notes

Buying processing time alone is not a fair enough model. Buying measured processing units is more defensible.

The strongest correlation is:

```text
media duration -> STT duration cost
media duration -> transcript length -> LLM token cost
```

But the relationship can vary:

- A fast-talking lecture creates more transcript tokens per minute than a sparse meeting.
- A long silent recording consumes STT duration but may generate fewer note tokens.
- A bad file or provider retry can cost more than a clean success.
- A user who regenerates notes multiple times creates extra LLM cost without extra media duration.
- Batch uploads can create queue pressure even if each file is individually affordable.

Therefore the user-facing model can be simple, but the backend ledger should preserve detailed cost evidence.

Recommended first pricing abstraction:

```text
processing units = transcription units + AI note units + regeneration units
```

Recommended internal tracking:

- `media_duration_seconds`
- `billable_processing_units`
- `transcription_units`
- `ai_note_units`
- `regeneration_units`
- `stt_provider`
- `stt_billable_seconds_estimate`
- `transcript_chars`
- `llm_provider`
- `llm_model`
- `llm_input_tokens`
- `llm_output_tokens`
- `llm_cost_estimate`
- `storage_source_mb`
- `storage_artifact_mb`
- `failure_or_retry_count`

This makes pricing adjustable after real usage without confusing early users.

## Shadow Billing Before Real Payment

Before enabling real recharge, the product should run shadow billing.

Shadow billing means:

- Do not charge the user.
- Do compute estimated processing units.
- Do record the cost ledger.
- Do show nothing or only internal/admin diagnostics.
- Do compare simulated revenue with real provider cost.

Minimum shadow-billing fields:

- Simulated processing units.
- Simulated sale amount.
- Estimated DeepSeek cost.
- Estimated Azure Speech cost after free allowance.
- Payment-fee estimate.
- Gross margin estimate.
- Whether the task would have been profitable.

This should happen before payment integration. Otherwise the first real paid users become the pricing experiment.

Recommended decision gate:

```text
Do not launch recharge until at least 30-50 real tasks have shadow-billing records.
```

This threshold is not statistically perfect, but it is enough to avoid blind pricing.

## Free Abuse And Multi-Account Risk

Per-account limits reduce cost but do not eliminate abuse.

Main bypass:

- A person can create many free accounts.

Countermeasures for the current stage:

- Registration rate limit by IP.
- Submission rate limit by IP.
- Global daily job limit.
- Global active job limit.
- Optional email verification later.
- Admin suspension.
- Detect repeated abuse patterns after real data exists.

Do not overbuild anti-abuse before traffic exists. But do not rely only on account quota.

The important layered model is:

```text
per-account limit
+ per-IP rate limit
+ global capacity limit
+ admin suspension
= acceptable beta risk
```

## Quota UX

Users should know why a limit exists and what to do next.

Bad:

```text
429 Too Many Requests
```

Better:

```text
当前账号的免费处理额度已用完。
充值后可继续处理新的音视频。
```

For active job limit:

```text
你已有 1 个任务正在处理中。
等当前任务完成后，可以继续上传下一个文件。
```

For global queue pressure:

```text
当前服务器任务较多。
你的文件可以进入队列，预计等待约 24-36 分钟。
```

Where possible, prefer queueing with wait estimate over rejecting. Reject only when the queue itself is full or cost risk is high.

## Logged-In Queue Behavior

Guests and logged-in users should not share exactly the same admission rules.

Recommended distinction:

- Guest queue is very small and trial-oriented.
- Logged-in queue can be larger but still bounded.
- Logged-in users should see their own queue position.
- Admin should be able to see global queue state.

For now, the existing job queue can serve both. Later, the system may need:

- Separate guest and account queues.
- Priority for logged-in users.
- Admin bypass or priority jobs.
- Better queue persistence if traffic grows.

Do not build a complex queue system before real usage proves it is needed.

## History Model

Logged-in account history should be one of the main account benefits.

History should include:

- Source filename.
- Task status.
- Created/updated time.
- Duration.
- STT provider and model profile.
- Summary status.
- Artifact download links.
- Edited transcript state.
- Failure reason if failed.

History should not show:

- Secret values.
- Raw provider credentials.
- Internal exception traces.

Default retention:

- Keep latest 20 tasks per user.
- Keep artifacts for 30 days.
- Delete source media after task completion unless needed temporarily for retranscription or playback.
- Keep compressed playback audio when useful for transcript review.

This is enough for a useful beta without becoming a full cloud storage product.

## Data Ownership And Privacy

Users should understand that uploaded media is processed by cloud services.

Minimum product copy:

```text
上传内容会用于生成字幕和笔记。当前云端转录由 Azure Speech 处理，摘要由配置的 AI 模型处理。任务完成后，原始上传文件会按保留策略清理。
```

This should be placed near account onboarding or upload settings, not as a scary legal wall.

Do not overpromise privacy.

Current product uses external STT and LLM services, so the honest promise is:

- We limit retention.
- We do not expose user tasks to other accounts.
- We avoid storing secrets in frontend.
- We clean source files after processing where possible.

## Minimum User Terms Before Recharge

Before any paid recharge is enabled, the product needs a small user-facing terms surface.

It does not need to be a full legal system at the beta stage, but it must explain:

- What processing units are.
- How processing units are estimated and finalized.
- That final charge may differ from the estimate within a disclosed range.
- What happens when processing fails.
- What happens when the user cancels.
- Whether starter balance expires.
- Whether paid balance expires.
- How uploaded media and generated artifacts are retained.
- That prices may change for future tasks.
- That historical charges are not retroactively recalculated.

Minimum copy direction:

```text
处理额度会按转录和 AI 笔记的实际消耗扣减。
任务开始前会冻结预计额度，完成后按实际消耗结算，多余额度会退回。
系统处理失败会退回未消耗额度。
试运行价格可能根据真实成本调整，但不会影响已完成任务。
```

Do not hide these rules only in a long legal page. The most important parts should appear near recharge and upload confirmation.

## Password And Account Recovery

Current account system has no password reset.

That means open registration is operationally weak.

Near-term policy:

- If a user forgets password, maintainer handles reset manually.
- Do not advertise account system as fully self-service.
- Keep signups closed unless manually supervised.

Medium-term requirements:

- Email delivery provider.
- Password reset token table.
- Reset email.
- Token expiry.
- Rate limit reset requests.
- Clear UI for reset flow.

Do not add password reset before deciding whether email is worth adding to this product.

## Email Verification

Email verification is not strictly required for invite-only accounts.

It becomes required if self-registration opens.

Without verification:

- Users can register with someone else's email.
- Password reset cannot be trusted.
- Abuse cleanup is harder.

Recommendation:

- Skip email verification for admin-created accounts.
- Require verification before public self-registration.

## Account Creation Modes

Possible modes:

### Maintainer-Created Account

Maintainer creates account manually or through admin UI.

Best for:

- First beta users.
- Friends, recruiters, collaborators.
- Serious users who request access.

### Invite Code

Maintainer creates an invite code; user signs up with it.

Best for:

- Slightly broader beta.
- Sharing access without manually setting passwords.

Needs:

- Invite token table.
- Expiry.
- Usage count.
- Optional quota profile.

### Open Signup

Anyone can register.

Best for:

- Later public launch.

Needs:

- Email verification.
- Password reset.
- Stronger quota system.
- User suspension.
- Abuse monitoring.

Recommendation:

Use maintainer-created account first, then invite codes or quiet signup, then open signup after quota display, cost observation, usage ledger, and suspension exist.

The product direction can still be open registration. The implementation should not start with unrestricted open registration.

## User Roles

Recommended roles:

- `admin`
- `user`
- `suspended`

Do not add many roles yet.

Avoid early roles like:

- `pro`
- `team`
- `student`
- `recruiter`
- `trial_plus`

Those are pricing or go-to-market concepts, not current product needs.

Role behavior:

| Role | Behavior |
| --- | --- |
| `admin` | Full app access, operations visibility, future user management |
| `user` | Normal logged-in workflow with account quotas |
| `suspended` | Cannot start new tasks, can possibly download existing results until retention ends |

If a user violates limits, suspension should stop new processing first. It does not need to delete their history immediately.

## Admin User Management

Admin UI does not need to be large.

Minimum useful admin functions:

- List users.
- See email, role, created time, last login.
- See recent task count and active jobs.
- Change role.
- Disable/suspend user.
- Reset password manually.
- See per-user quota usage.

Do not build analytics dashboards before these basics.

Admin user list should avoid exposing full task content by default. It can show counts and status, with drilldown later if needed.

## Account Settings

Normal user account settings should be minimal:

- Email display.
- Logout.
- Password change.
- Usage/limits summary.
- Retention explanation.

Do not add profile avatars, names, teams, billing address, or organization settings yet.

For FluentFlow's current goal, those are noise.

## Logged-In Feature Boundary

Account-only features should be:

- Task history.
- Batch upload.
- Longer files.
- More available processing balance.
- Cross-device result access.
- Saved transcript edits.
- Optional Feishu export.
- Guest result claim, later.

Guest-available features should be:

- One real trial upload.
- View generated transcript and note.
- Download own temporary result.

Admin-only features should be:

- Ops status.
- User management.
- Quota override.
- System cleanup or maintenance.

## Feishu Export Boundary

For logged-in users, Feishu export should not be enabled casually.

There are two different export models:

1. Export through maintainer-owned Feishu app or lark-cli.
2. Export through user-connected Feishu account.

The first is simpler but can mix user output into maintainer-controlled Feishu space.

The second is cleaner but requires OAuth or user credential connection.

Recommendation for now:

- Guests: no Feishu export.
- Normal accounts: manual download first; Feishu export only if explicitly enabled.
- Admin: can use Feishu export for personal workflow and demos.

Do not position Feishu export as a public logged-in user feature until the destination and permissions are clear.

## Security Baseline

Minimum requirements:

- Passwords hashed in account store.
- Sessions are httponly cookies.
- Secure cookies in HTTPS deployment.
- Account-scoped job queries.
- Account-scoped artifact downloads.
- No secrets in frontend localStorage.
- Rate limits on login and registration.
- No detailed auth error that reveals whether an email exists.

Current likely gaps to check before public signup:

- Login rate limiting.
- Registration rate limiting.
- Password reset absence.
- Email verification absence.
- Admin UI absence.
- User suspension absence.

These are manageable for quota-limited free accounts during beta if global limits remain conservative. They are not acceptable for high-volume paid self-serve growth.

## UX Copy Direction

Top-right account area for visitor:

```text
访客试用
登录
```

After guest success:

```text
结果已生成
你可以下载字幕和笔记。登录账号后，可保存更多任务历史并处理更长材料。
```

When account-only feature is clicked:

```text
登录后可使用此功能
账号用于保存历史、跨设备查看结果，并管理你的处理额度。
```

When registration is closed:

```text
当前暂未开放自助注册。
你可以先使用访客试用；如需长期使用，请联系维护者开通账号。
```

When registration is open with free limits:

```text
创建免费账号
保存历史、跨设备查看结果，并获得基础处理额度。
```

When free quota is used up:

```text
免费处理额度已用完。
充值后可继续处理新的音视频。
```

When recharge is later available:

```text
需要处理更多文件？
充值后按转录和 AI 笔记的实际消耗扣减额度，用多少花多少。
```

When logged in:

```text
已登录
历史记录会保存在当前账号下。
```

## Suggested Phased Implementation

The first implementation should not start with payment provider integration, public registration, or complex pricing.

The first implementation should build the paid-account foundation:

```text
account identity
+ starter balance
+ balance ledger
+ task admission by balance
+ reservation/final charge/refund
+ user-facing quota state
+ admin manual adjustment
+ shadow billing
```

This is the minimum useful base before real recharge. It lets the product test whether the account/quota model works while keeping payment collection manual or disabled.

### First Landing Scope

Build this first:

1. Balance and ledger model.
2. Free starter balance for new registered users.
3. Upload-time quota estimate and admission check.
4. Task reservation before queue entry.
5. Final charge, reservation release, and refund behavior after task completion/failure.
6. User-facing remaining balance, estimated consumption, and insufficient-balance state.
7. Admin manual balance adjustment for beta/manual recharge and support.
8. Shadow billing records for real cost, simulated revenue, and margin.

Do not include in the first landing scope:

- Automated WeChat/Alipay/Stripe payment.
- Public open registration at scale.
- Password reset.
- Email verification.
- Complex paid packages.
- Free-form recharge amount.
- Guest result claiming.
- Queue priority tiers.
- Team or organization accounts.

The first version should answer:

```text
Can users understand balance?
Can tasks be safely admitted or blocked by balance?
Can the system reserve and settle usage without losing track?
Can the maintainer manually compensate or top up users?
Can real usage data support a future price?
```

If these answers are not reliable, automated payment will only create support and accounting problems.

### Phase 0: Cost Observation And Shadow Billing

Goal: learn real cost before charging users.

Work:

- Record media duration, STT provider, transcript length, LLM token usage, retries, and storage size per task.
- Estimate DeepSeek cost per task.
- Estimate Azure Speech billable usage after free allowance.
- Calculate simulated processing units.
- Calculate simulated revenue and margin.
- Add admin-only visibility for task-level cost diagnostics.

This phase should start before recharge work. It makes later pricing less speculative.

This phase can run alongside the first balance implementation. It does not need to be visible to normal users at first.

### Phase 1: Account UX Clarification

Goal: make existing account system understandable and prepare the user for quota-based usage.

Work:

- Keep guest as default entry.
- Add visible login entry.
- Make registration mode explicit: closed, open free, or invite.
- If open free registration is enabled, show limits before signup.
- Show logged-in state clearly.
- Explain account benefits after guest completion.
- Explain that registered accounts receive a starter balance.
- Explain that more usage will later require recharge.

This phase mostly affects frontend wording and routing.

### Phase 2: Balance Ledger And Starter Balance

Goal: add the foundation for quota-based account usage without payment.

Work:

- Add balance transaction ledger.
- Add cached account balance if useful, but keep ledger as source of truth.
- Grant one-time starter balance to new registered users.
- Record starter grant as a `starter_grant` ledger transaction.
- Add rate-card version field to usage-related transactions.
- Add admin-safe helpers to recompute balance from ledger.
- Add tests for grant idempotency and ledger balance correctness.

This phase should happen before any task-level quota enforcement. Otherwise "balance" becomes a display number instead of a reliable control surface.

### Phase 3: Task Admission, Reservation, And Settlement

Goal: make processing consume account balance in a controlled way.

Work:

- Estimate processing units before accepting a task.
- Block new task submission when balance is insufficient.
- Reserve estimated balance before the task enters queue.
- Finalize charge after successful processing.
- Release unused reserved balance.
- Refund or release reservation on validation failure, queue cancellation, and system failure.
- Record transcript/AI usage metrics needed for final charge and shadow billing.
- Keep global/server safety limits above account balance.
- Add tests for insufficient balance, reservation, final charge, failed task refund, and duplicate-submit safety.

This phase is the real "pay-as-you-go" behavior, even before real money exists.

### Phase 4: Logged-In Limits And History UX

Goal: make account value and boundaries clear.

Work:

- Display account quota summary.
- Display estimated consumption before upload when possible.
- Improve errors for per-user active job and insufficient balance.
- Make task history feel account-based.
- Ensure downloads and transcript edits are account-scoped.
- Show clear post-task final charged amount and remaining balance.
- Add tests for account-scoped artifacts and transcript edits.

This phase improves trust and reduces confusion.

### Phase 5: Admin User Management And Manual Recharge

Goal: let maintainer operate early user accounts and manually add balance without touching SQLite.

Work:

- Admin-only user list.
- Create user.
- Change role.
- Suspend user.
- Manual password reset.
- Basic usage view.
- View user balance and recent ledger transactions.
- Add manual balance adjustment.
- Require an adjustment reason.
- Optionally record external payment note/reference for manual beta recharge.

This phase enables controlled beta access and manual paid testing. It is the correct first recharge path.

#### Thin Admin Balance UI

The first admin UI should be deliberately thin.

Goal:

```text
Let the maintainer find a user, inspect their current balance and recent balance ledger, then manually add or deduct processing units with a recorded reason.
```

Entry:

- Only visible to `admin` users.
- Add a sidebar item named `管理` / `Admin`.
- If a non-admin reaches the route directly, show a permission error or rely on backend `403`.

Layout:

- One admin page is enough.
- Left or top area: user list.
- Right or lower area: selected user detail.
- Avoid analytics dashboards, charts, and large operations panels.

User list fields:

- Email.
- Role.
- Status if available.
- Current balance.
- Created time.
- Last login time.

Selected user detail:

- Current balance.
- Recent balance transactions, latest 20 is enough.
- Transaction columns:
  - created time
  - transaction type
  - unit delta
  - balance after
  - reason
  - task id if any
  - provider/reference if any

Manual adjustment form:

- `units`: required integer. Positive means add quota; negative means deduct quota.
- `reason`: required.
- `provider_reference`: optional, for manual payment note or external reference.

Required states:

- Loading users.
- Empty user list.
- Selected user loading/refreshing after adjustment.
- Adjustment success.
- Adjustment failure.
- Permission denied.

First version should not include:

- Create user.
- Change role.
- Suspend user.
- Password reset.
- Payment order creation.
- WeChat/Alipay QR code.
- Recharge package management.
- Charts or revenue analytics.
- Full task content inspection.

Existing backend endpoints for the first version:

```text
GET /admin/users
POST /admin/users/{user_id}/balance-adjustments
```

If the UI needs more detail later, add narrow admin endpoints instead of exposing raw database access.

### Phase 6: Open Free Registration Hardening

Goal: make public free accounts safe enough for broader promotion.

Work:

- Registration rate limiting.
- Optional email verification.
- Account suspension in admin UI.
- Quota usage view.
- Better multi-account abuse monitoring.
- Clear starter-balance and account-limit copy.

This phase is required before actively promoting registration at scale.

### Phase 7: Metered Recharge Foundation

Goal: prepare the product for automated paid functionality without coupling the app to one payment provider.

Work:

- Add purchase order fields.
- Define starter balance and paid-balance behavior.
- Define starter-balance and promotional-balance expiration.
- Add rate-card versioning.
- Add payment-provider abstraction boundary.
- Keep request admission driven by balance and safety limits.
- Add admin override for balance testing and support.

Do this before integrating a payment provider.

### Phase 8: Payment Provider Integration

Goal: paid recharge.

Work:

- Hosted checkout.
- Webhook handling.
- Purchase confirmation.
- Balance grant.
- Refund or failed-payment handling.
- User-facing recharge and balance states.
- User-facing insufficient-balance and payment-failed states.

Do not start here. Payment should sit on top of a proven balance and usage-ledger system.

## Recommended Immediate Direction

The next product step should be:

1. Keep current guest trial public.
2. Keep registration controlled until quota UI, admin suspension, and rate limits exist.
3. Improve login/register UI copy so visitors understand accounts are for saved history and starter balance.
4. Add starter balance and append-only balance ledger.
5. Add upload-time quota estimate, reservation, final charge, release, and refund.
6. Add visible quota summary for logged-in users.
7. Add admin manual balance adjustment before any automated payment provider.
8. Add shadow billing and cost diagnostics.
9. Keep global server limits as the ultimate protection.

This gives FluentFlow a clean public story:

```text
任何人都能试用。
注册免费账号可保存历史并获得基础额度。
未来可充值继续按量使用。
```

That is better aligned with later paid functionality than a purely invitation-based account model.

## Open Questions

These should be decided before implementation:

1. Should free registration open immediately, or only after quota UI and admin suspension exist?
2. Should a guest result be claimable into an account in the first account phase?
3. Should logged-in users get Feishu export, or only downloads for now?
4. What normal-user quota should launch with on the current ECS instance?
5. Should account users see their remaining quota before upload?
6. Do we want password reset soon, or accept manual reset during beta?
7. What minimum anti-abuse layer is required before public free registration?
8. What should the first processing-unit formula be?
9. Should note regeneration consume additional balance in the first paid version?
10. What overage buffer is acceptable between estimated and final charge?
11. Should paid balance ever expire?
12. What minimum shadow-billing sample size is enough before launching recharge?

## Default Answers If No Further Decision Is Made

If we need to proceed without more discussion, use these defaults:

- Registration mode: open free registration is acceptable only with hard quotas; otherwise keep closed until quota UI and admin suspension exist.
- Account creation: open free account is the target direction; start with admin-created or invite accounts until quota UI, usage ledger, cost observation, and suspension exist.
- Invite codes: optional, not the main path if recharge accounts are planned.
- Guest result claim: later.
- Logged-in Feishu export: disabled for normal users initially.
- Normal user active jobs: 1.
- Normal user waiting jobs: 3.
- Registered user starter balance: 100 processing units.
- Registered user paid balance: purchased processing units.
- Normal user max single upload: 1 GB.
- Normal user max media duration: 2 hours.
- History retention: latest 20 tasks.
- Artifact retention: 30 days.
- Password reset: manual maintainer reset during beta.
- Paid model: metered recharge and usage ledger first, payment provider integration later.
- First paid unit: processing units calculated from transcription usage and AI note usage, with internal token/cost tracking.
- Shadow billing: required before real recharge.
- Shadow-billing sample size before launch: at least 30-50 real tasks.
- Balance ledger: append-only transaction ledger, cached balance is secondary.
- Reservation policy: reserve estimate before processing, finalize after completion.
- Overage policy: cap beta overage at reservation plus 10%-20%; do not silently make normal users negative.
- Refund policy: refund unused or failed portions, charge successfully consumed expensive stages.
- Starter balance expiration: 30 days.
- Paid balance expiration: no expiration during beta unless payment provider or local law requires it.
- Rate card: every reservation and final charge records a rate-card version.

These defaults are intentionally conservative.
