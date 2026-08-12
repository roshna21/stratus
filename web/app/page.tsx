import Link from "next/link";
import type { ReactNode } from "react";
import { Badge, Card, SectionHeading, buttonClass } from "@/components/ui";

/**
 * The landing page.
 *
 * Deliberately static and server-rendered: it makes no request to the API,
 * so it looks right to someone who has only opened the link and has no
 * server running. Everything shown here is real output the product actually
 * produces — the approval card below is the wording from a genuine build,
 * not a mockup written to look good.
 */
export default function LandingPage() {
  return (
    <>
      <Hero />
      <StatsBand />
      <Problem />
      <BeforeAfter />
      <Pipeline />
      <Pricing />
      <TheCatch />
      <Refuses />
      <Capabilities />
      <Architecture />
      <Stack />
      <FinalCall />
    </>
  );
}

/* -------------------------------------------------------------------------
 * Hero
 * ---------------------------------------------------------------------- */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="aurora drift" aria-hidden />
      <div className="grid-backdrop" aria-hidden />

      <div className="relative mx-auto max-w-6xl px-5 pb-20 pt-20 sm:pt-28">
        <div className="mx-auto max-w-3xl text-center">
          <div className="fade-in flex justify-center">
            <Badge tone="accent">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              Runs against a real Azure subscription
            </Badge>
          </div>

          {/* The gradient is applied to the whole heading, not one line of
              it. Scoped to a single line, background-clip squeezes the full
              range into that line and it reads as one grey word above one
              white word — a rendering fault rather than a treatment. */}
          <h1 className="text-gradient rise mt-7 text-balance text-[2.75rem] font-semibold leading-[1.05] tracking-[-0.035em] sm:text-display">
            Infrastructure
            <br />
            from <span className="text-lilac">a sentence</span>.
          </h1>

          <p className="rise mx-auto mt-6 max-w-xl text-pretty text-[16.5px] leading-relaxed text-fg-muted">
            Describe what you need in plain English. An agent designs it, shows you
            exactly what would change and what it would cost, and builds it on Azure
            once you agree.
          </p>

          <p className="rise mx-auto mt-4 max-w-lg text-pretty text-[15px] leading-relaxed text-fg-faint">
            You never see infrastructure code. You never learn a cloud console. You have
            a conversation.
          </p>

          <div className="rise mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link href="/build" className={buttonClass("primary", "lg")}>
              Open the app
              <Arrow />
            </Link>
            <a
              href="https://github.com/roshna21/stratus"
              target="_blank"
              rel="noreferrer"
              className={buttonClass("normal", "lg")}
            >
              Read the source
            </a>
          </div>

          <p className="mt-5 font-mono text-[11.5px] tracking-wide text-fg-faint">
            367 tests · none touch a network, a cloud account, or a model
          </p>
        </div>

        <div className="relative mx-auto mt-16 max-w-3xl">
          <ApprovalPreview />
        </div>
      </div>
    </section>
  );
}

/**
 * The approval step, reproduced.
 *
 * This is the product's whole argument in one picture, so it is worth
 * showing rather than describing. The words are copied from a real build of
 * “a small website that can store uploaded files” — including the cost
 * lines, which are the part people do not expect.
 */
function ApprovalPreview() {
  return (
    <div className="grad-ring relative rounded-2xl bg-surface shadow-[0_30px_90px_-24px_var(--color-violet-deep)]">
      <div className="flex items-center gap-2 border-b border-hairline px-4 py-3">
        <span className="h-2.5 w-2.5 rounded-full bg-edge" />
        <span className="h-2.5 w-2.5 rounded-full bg-edge" />
        <span className="h-2.5 w-2.5 rounded-full bg-edge" />
        <span className="ml-2 font-mono text-[11px] text-fg-faint">stratus — build</span>
      </div>

      <div className="space-y-4 p-5 sm:p-6">
        <div className="flex justify-end">
          <div className="max-w-[85%] rounded-xl rounded-br-sm border border-accent/25 bg-accent/10 px-4 py-2.5 text-left text-sm">
            a small website that can store uploaded files
          </div>
        </div>

        <div className="rounded-xl border border-hairline bg-raised p-5 text-left">
          <p className="text-sm leading-relaxed">
            A website, with a dedicated folder alongside it for storing uploaded files.
          </p>

          <div className="mt-5 flex flex-wrap items-center gap-2.5">
            <Badge tone="ok">no fixed monthly charge</Badge>
            <Badge>4 things created</Badge>
            <Badge>nothing destroyed</Badge>
          </div>

          <div className="mt-5">
            <div className="mb-3 font-mono text-[10.5px] uppercase tracking-[0.13em] text-fg-faint">
              What would change
            </div>
            <div className="space-y-2.5 rounded-lg border border-hairline bg-canvas p-4">
              <ChangeLine tone="ok">place to keep files (website)</ChangeLine>
              <ChangeLine tone="ok">folder (uploads)</ChangeLine>
              <ChangeLine tone="ok">
                plus 2 supporting pieces needed to make that work
              </ChangeLine>
              <p className="pt-1.5 text-[13px] text-fg-faint">
                These cost nothing to exist, and bill on what you use — about 2 cents per
                GB stored per month.
              </p>
            </div>
          </div>

          <div className="mt-5 flex items-center gap-2.5">
            <span className={buttonClass("primary", "sm")}>Build it</span>
            <span className={buttonClass("normal", "sm")}>Cancel</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChangeLine({ children, tone }: { children: ReactNode; tone: "ok" | "danger" }) {
  return (
    <div className="flex items-start gap-2.5 font-mono text-[12.5px] leading-relaxed">
      <span className={tone === "ok" ? "text-ok" : "text-danger"}>
        {tone === "ok" ? "+" : "−"}
      </span>
      <span className={tone === "ok" ? "text-fg-muted" : "text-danger/90"}>
        {children}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------
 * Numbers
 * ---------------------------------------------------------------------- */

function StatsBand() {
  const stats = [
    { n: "367", label: "tests", sub: "none touch a cloud" },
    { n: "10", label: "steps", sub: "sentence to running" },
    { n: "1", label: "model call", sub: "the other nine are code" },
    { n: "$0", label: "spent", sub: "building all of it" },
  ];

  return (
    <section className="border-y border-hairline bg-surface/40">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-px bg-hairline lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="bg-canvas px-6 py-9 text-center">
            <div className="text-lilac font-mono text-[2.5rem] leading-none">{s.n}</div>
            <div className="mt-3 text-[14px] font-medium">{s.label}</div>
            <div className="mt-1 text-[12.5px] text-fg-faint">{s.sub}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * The problem
 * ---------------------------------------------------------------------- */

function Problem() {
  return (
    <section>
      <div className="mx-auto max-w-6xl px-5 py-24">
        <SectionHeading eyebrow="The problem" title="A file is not a deployment.">
          AI coding tools will happily write you a configuration file. What they will not
          do is own the consequences.
        </SectionHeading>

        <div className="mt-12 grid gap-px overflow-hidden rounded-xl border border-hairline bg-hairline sm:grid-cols-2 lg:grid-cols-4">
          {[
            {
              t: "They don’t know what you have",
              d: "So they build duplicates of things already sitting in your account.",
            },
            {
              t: "They don’t show you first",
              d: "The change happens, and then you find out what the change was.",
            },
            {
              t: "They can’t recover",
              d: "A deployment dies halfway and leaves the account in a broken half-built state.",
            },
            {
              t: "They don’t count the cost",
              d: "Something that bills $32 a month forever, handed over cheerfully.",
            },
          ].map((item) => (
            <div key={item.t} className="bg-surface p-6">
              <h3 className="text-[15px] font-medium leading-snug text-balance">
                {item.t}
              </h3>
              <p className="mt-2.5 text-[13.5px] leading-relaxed text-fg-muted">
                {item.d}
              </p>
            </div>
          ))}
        </div>

        <p className="mt-10 text-[17px] font-medium tracking-tight">
          Stratus owns the whole lifecycle.
        </p>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * What you type against what it writes
 * ---------------------------------------------------------------------- */

/**
 * The trade the product is offering, shown rather than claimed.
 *
 * Showing the configuration is not a contradiction of hiding it — the whole
 * proposition is that this exists and is not your problem. Naming what you
 * are being spared is more persuasive than asserting you are being spared
 * something.
 */
function BeforeAfter() {
  return (
    <section className="relative overflow-hidden border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-24">
        <SectionHeading eyebrow="The trade" title="One sentence in. This out.">
          Both describe the same website. Only one of them is your problem.
        </SectionHeading>

        <div className="mt-12 grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
          <Card className="grad-ring flex flex-col justify-center p-7">
            <div className="font-mono text-[10.5px] uppercase tracking-[0.13em] text-accent">
              What you type
            </div>
            <p className="mt-5 text-[22px] leading-snug tracking-tight text-balance">
              a small website that can store uploaded files
            </p>
            <p className="mt-6 text-[13.5px] leading-relaxed text-fg-muted">
              No resource names. No region. No tier, replication setting or TLS version.
              You are not expected to know that those are decisions.
            </p>
          </Card>

          <Card className="relative overflow-hidden p-0">
            <div className="flex items-center justify-between border-b border-hairline px-5 py-3">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.13em] text-fg-faint">
                What it writes
              </span>
              <Badge>you never see this</Badge>
            </div>
            <pre className="overflow-x-auto px-5 py-4 font-mono text-[12px] leading-[1.75] text-fg-faint">
              <Code />
            </pre>
          </Card>
        </div>
      </div>
    </section>
  );
}

/** Coloured by hand rather than by a highlighter dependency — it is eight
 *  lines of one language that never changes. */
function Code() {
  return (
    <code>
      <span className="text-accent">resource</span>{" "}
      <span className="text-ok">“azurerm_storage_account”</span>{" "}
      <span className="text-ok">“website”</span> {"{"}
      {"\n  name                     = "}
      <span className="text-ok">“webr0bhza”</span>
      {"\n  resource_group_name      = azurerm_resource_group.main.name"}
      {"\n  location                 = "}
      <span className="text-ok">“eastus”</span>
      {"\n  account_tier             = "}
      <span className="text-ok">“Standard”</span>
      {"\n  account_replication_type = "}
      <span className="text-ok">“LRS”</span>
      {"\n  min_tls_version          = "}
      <span className="text-ok">“TLS1_2”</span>
      {"\n\n  "}
      <span className="text-accent">static_website</span> {"{"}
      {"\n    index_document = "}
      <span className="text-ok">“index.html”</span>
      {"\n  }"}
      {"\n}"}
    </code>
  );
}

/* -------------------------------------------------------------------------
 * How it works
 * ---------------------------------------------------------------------- */

const STEPS = [
  "read what already exists",
  "write configuration for the request",
  "check it parses",
  "work out exactly what would change",
  "refuse it if it is unsafe, and try again",
  "price it",
  "explain it, in plain English",
  "wait for your approval",
  "build it, streaming progress",
  "recover if it fails partway",
];

function Pipeline() {
  return (
    <section id="how" className="scroll-mt-16 border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-24">
        <SectionHeading eyebrow="How it works" title="Ten steps. One of them is a model.">
          Terraform runs underneath — an implementation detail the user never sees. The
          agent writes it, runs it, reads its output, and translates everything back into
          plain language.
        </SectionHeading>

        <ol className="mt-12 grid gap-px overflow-hidden rounded-xl border border-hairline bg-hairline sm:grid-cols-2">
          {STEPS.map((step, i) => {
            // Step 2 is the only one that calls a language model. Marking it
            // here is the entire point of the section — the claim is that
            // everything else is ordinary, deterministic code.
            const isModel = i === 1;
            return (
              <li
                key={step}
                className={`flex items-start gap-4 p-5 ${
                  isModel ? "bg-accent/[0.07]" : "bg-surface"
                }`}
              >
                <span
                  className={`mt-px flex h-6 w-6 shrink-0 items-center justify-center rounded-md font-mono text-[11px] ${
                    isModel
                      ? "bg-accent text-canvas"
                      : "border border-hairline bg-raised text-fg-faint"
                  }`}
                >
                  {i + 1}
                </span>
                <div className="min-w-0">
                  <p
                    className={`text-[14.5px] leading-snug ${
                      isModel ? "text-fg" : "text-fg-muted"
                    }`}
                  >
                    {step}
                  </p>
                  {isModel && (
                    <p className="mt-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-accent">
                      the only model call
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>

        <p className="mt-8 max-w-2xl text-[15px] leading-relaxed text-fg-muted">
          Everything else has exactly one correct answer, so it is ordinary code —
          instant, free, and identical every time.
        </p>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Cost
 * ---------------------------------------------------------------------- */

/**
 * The three answers Stratus gives about money, and the fourth it refuses to
 * give. Bar widths are illustrative of the categories, not a benchmark —
 * the real figures come from Azure's price list when a plan is made.
 */
const COST_BANDS = [
  {
    label: "Free to exist",
    example: "groups, folders, the wiring between them",
    width: "8%",
    tone: "bg-ok",
  },
  {
    label: "Bills on what you use",
    example: "storage — about 2 cents per GB per month",
    width: "34%",
    tone: "bg-warn",
  },
  {
    label: "Charges every hour",
    example: "always-on servers and databases",
    width: "88%",
    tone: "bg-danger",
  },
];

function Pricing() {
  return (
    <section className="relative overflow-hidden border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-24">
        <SectionHeading
          eyebrow="Cost"
          title="Priced from Azure’s own list, before you agree."
        >
          Every resource in a plan is sorted into one of three bands and totalled, using
          the public retail price list. No key, no estimate pulled out of the air.
        </SectionHeading>

        <div className="mt-12 space-y-5">
          {COST_BANDS.map((band, i) => (
            <div key={band.label}>
              <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <span className="text-[14.5px] font-medium">{band.label}</span>
                <span className="text-[13px] text-fg-muted">{band.example}</span>
              </div>
              <div className="h-2.5 overflow-hidden rounded-full bg-raised">
                <div
                  className={`grow-bar h-full rounded-full ${band.tone}`}
                  style={{ width: band.width, animationDelay: `${i * 0.14}s` }}
                />
              </div>
            </div>
          ))}
        </div>

        <Card tone="accent" className="mt-10 p-6">
          <p className="text-[15px] leading-relaxed">
            <strong className="font-medium">And a fourth answer: unknown.</strong> A
            resource that cannot be priced is reported as unknown, out loud, and never
            folded into the total as free. A wrong “this is free” is how someone finds a
            surprise on a bill.
          </p>
        </Card>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * The moment worth showing
 * ---------------------------------------------------------------------- */

function TheCatch() {
  return (
    <section className="relative overflow-hidden border-t border-hairline">
      <div className="glow left-1/3 top-0 h-72 w-[40rem] bg-danger/10" aria-hidden />
      <div className="relative mx-auto max-w-6xl px-5 py-24">
        <div className="grid items-center gap-14 lg:grid-cols-2">
          <div>
            <SectionHeading
              eyebrow="The deletion gate"
              title="This request would have destroyed a working website."
            >
              Asking for “a place to keep backup files” in a workspace that already held
              a website is not a strange thing to type. One set of infrastructure lives
              in one workspace, so the new request replaces the old one — that is
              Terraform’s model, and it is exactly the sort of thing that is discovered
              afterwards.
            </SectionHeading>

            <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-fg-muted">
              Stratus reads the plan rather than the generated text, so a setting written
              three different ways is still caught. It says what would be lost, in plain
              words, and then refuses to move until the word{" "}
              <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[13px] text-danger">
                DELETE
              </code>{" "}
              is typed exactly. An empty answer is never consent.
            </p>
          </div>

          <Card tone="danger" className="p-6">
            <div className="flex items-center gap-2.5 rounded-lg bg-danger/10 px-3.5 py-2.5 text-[13.5px] text-danger">
              <strong className="font-semibold">This will destroy things.</strong>
              <span className="text-danger/80">Read it carefully.</span>
            </div>

            <div className="mt-5">
              <div className="mb-3 font-mono text-[10.5px] uppercase tracking-[0.13em] text-fg-faint">
                What would change
              </div>
              <div className="space-y-2.5 rounded-lg border border-hairline bg-canvas p-4">
                <ChangeLine tone="danger">
                  website — and everything stored in it
                </ChangeLine>
                <ChangeLine tone="danger">folder (uploads)</ChangeLine>
                <ChangeLine tone="ok">place to keep files (backups)</ChangeLine>
              </div>
            </div>

            <div className="mt-5">
              <p className="text-[13.5px] text-fg-muted">
                To go ahead, type <code className="font-mono text-danger">DELETE</code>{" "}
                exactly.
              </p>
              <div className="mt-3 flex flex-wrap gap-2.5">
                <span className="w-32 rounded-lg border border-hairline bg-canvas px-3 py-2 font-mono text-sm text-fg-faint">
                  |
                </span>
                <span
                  className={`${buttonClass("danger", "md")} pointer-events-none opacity-40`}
                >
                  Destroy and build
                </span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * What it will not build
 * ---------------------------------------------------------------------- */

const REFUSALS = [
  {
    t: "Storage the whole internet can read",
    d: "The single most common way a weekend project leaks its users’ files.",
  },
  {
    t: "SSH open to every address",
    d: "A door onto the public internet that is scanned within minutes of existing.",
  },
  {
    t: "Transfer without encryption",
    d: "Silently downgrades everything sent to it, and nothing warns you.",
  },
];

function Refuses() {
  return (
    <section className="border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-24">
        <SectionHeading
          eyebrow="Safety"
          title="It refuses, then quietly fixes it."
        >
          The refusal is not shown to you as an error. It goes back to the model, which
          rewrites the configuration — so what reaches the approval screen is the safe
          version, and the only trace is a small note saying how many attempts were
          rejected.
        </SectionHeading>

        <div className="mt-12 grid gap-4 sm:grid-cols-3">
          {REFUSALS.map((r) => (
            <Card key={r.t} interactive className="p-5">
              <div className="mb-3.5 flex h-8 w-8 items-center justify-center rounded-lg bg-danger/10 font-mono text-[13px] text-danger">
                ✕
              </div>
              <h3 className="text-[14.5px] font-medium leading-snug text-balance">
                {r.t}
              </h3>
              <p className="mt-2.5 text-[13.5px] leading-relaxed text-fg-muted">{r.d}</p>
            </Card>
          ))}
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Badge tone="accent">1 unsafe version rejected</Badge>
          <span className="text-[13.5px] text-fg-muted">
            — what you actually see on the approval card.
          </span>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Capabilities
 * ---------------------------------------------------------------------- */

const CAPABILITIES = [
  {
    t: "Knows what already exists",
    d: "The account is read before anything is planned. Asking twice does not build twice.",
  },
  {
    t: "Shows the change first",
    d: "Every action is a reviewed diff, described in plain English. Terraform vocabulary never reaches the screen.",
  },
  {
    t: "Prices it before you agree",
    d: "What is free, what bills on usage, and what charges every hour — from Azure’s public price list.",
  },
  {
    t: "Refuses unsafe configurations",
    d: "World-readable storage, SSH open to the internet, unencrypted transfer. You see the safe version, not an error.",
  },
  {
    t: "Recovers from a half-built state",
    d: "If a build dies partway it works out what survived, and offers to finish or undo it.",
  },
  {
    t: "Notices changes made elsewhere",
    d: "When something moves in the Azure portal outside Stratus, it says so, and says what it means.",
  },
  {
    t: "Records every change",
    d: "Each one stored with the configuration that produced it. Roll back to any of them.",
  },
  {
    t: "Never reports zero when unsure",
    d: "A resource that cannot be priced is called unknown, out loud, and never folded into the total as free.",
  },
];

function Capabilities() {
  return (
    <section id="capabilities" className="scroll-mt-16 border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-24">
        <SectionHeading
          eyebrow="What it does"
          title="More than a code generator, in eight specific ways."
        />

        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {CAPABILITIES.map((c) => (
            <Card key={c.t} interactive className="p-5">
              <h3 className="text-[14.5px] font-medium leading-snug text-balance">
                {c.t}
              </h3>
              <p className="mt-2.5 text-[13.5px] leading-relaxed text-fg-muted">{c.d}</p>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * What four things actually means
 * ---------------------------------------------------------------------- */

/**
 * The approval card says “4 things created”. This is what those four are.
 *
 * Drawn as an SVG rather than nested boxes because the shape of the answer
 * — one group holding one account holding two things — is the point, and
 * that is a structure rather than a list.
 */
function Architecture() {
  return (
    <section className="border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-24">
        <SectionHeading eyebrow="Under the plan" title="What “4 things created” means.">
          The sentence asked for a website and somewhere to put uploads. Two of these
          are what you asked for. Two exist because Azure requires them, and you were
          never asked to know that.
        </SectionHeading>

        <Card className="mt-12 overflow-x-auto p-7">
          <svg
            viewBox="0 0 720 260"
            className="min-w-[620px]"
            role="img"
            aria-label="A resource group contains a storage account, which contains a static website and an uploads folder."
          >
            <rect
              x="10"
              y="20"
              width="700"
              height="220"
              rx="14"
              fill="none"
              stroke="var(--color-hairline)"
              strokeDasharray="5 5"
            />
            <text x="30" y="48" className="fill-fg-faint" fontSize="12" fontFamily="var(--font-mono)">
              group (rg-website-uploads)
            </text>

            <rect
              x="40"
              y="70"
              width="240"
              height="140"
              rx="12"
              fill="var(--color-raised)"
              stroke="var(--color-accent)"
              strokeOpacity="0.45"
            />
            <text x="64" y="112" className="fill-fg" fontSize="15" fontWeight="500">
              place to keep files
            </text>
            <text x="64" y="136" className="fill-fg-faint" fontSize="12" fontFamily="var(--font-mono)">
              webr0bhza
            </text>
            <text x="64" y="168" className="fill-fg-muted" fontSize="12">
              Holds both of the things
            </text>
            <text x="64" y="186" className="fill-fg-muted" fontSize="12">
              on the right.
            </text>

            <path
              d="M280 118 H 400"
              className="draw"
              stroke="var(--color-accent)"
              strokeOpacity="0.6"
              strokeWidth="1.5"
              fill="none"
            />
            <path
              d="M280 162 H 400"
              className="draw"
              stroke="var(--color-accent)"
              strokeOpacity="0.6"
              strokeWidth="1.5"
              fill="none"
              style={{ animationDelay: "0.2s" }}
            />

            <rect
              x="400"
              y="82"
              width="280"
              height="72"
              rx="12"
              fill="var(--color-surface)"
              stroke="var(--color-hairline)"
            />
            <text x="424" y="112" className="fill-fg" fontSize="14" fontWeight="500">
              the website itself
            </text>
            <text x="424" y="134" className="fill-fg-faint" fontSize="12">
              serves index.html to the public
            </text>

            <rect
              x="400"
              y="166"
              width="280"
              height="60"
              rx="12"
              fill="var(--color-surface)"
              stroke="var(--color-hairline)"
            />
            <text x="424" y="192" className="fill-fg" fontSize="14" fontWeight="500">
              folder (uploads)
            </text>
            <text x="424" y="212" className="fill-fg-faint" fontSize="12">
              private, for stored files
            </text>
          </svg>
        </Card>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Stack
 * ---------------------------------------------------------------------- */

const STACK = [
  ["Agent", "Python, FastAPI"],
  ["Reasoning", "Gemini by default; Claude supported, behind one interface"],
  ["Infrastructure engine", "Terraform CLI, azurerm provider"],
  ["Cloud", "Microsoft Azure"],
  ["State", "Azure Storage, with locking"],
  ["Pricing", "Azure Retail Prices API — public, no key"],
  ["Interface", "Command line, and Next.js 16 / React 19 / Tailwind 4"],
  ["Tests", "367, none touching a network, a cloud account, or a model"],
];

function Stack() {
  return (
    <section id="stack" className="scroll-mt-16 border-t border-hairline">
      <div className="mx-auto max-w-6xl px-5 py-24">
        <SectionHeading eyebrow="Stack" title="What it is made of." />

        <div className="mt-10 overflow-hidden rounded-xl border border-hairline">
          {STACK.map(([layer, choice], i) => (
            <div
              key={layer}
              className={`flex flex-col gap-1 px-5 py-4 sm:flex-row sm:items-baseline sm:gap-8 ${
                i % 2 ? "bg-surface" : "bg-canvas"
              }`}
            >
              <div className="w-full shrink-0 font-mono text-[11px] uppercase tracking-[0.12em] text-fg-faint sm:w-52">
                {layer}
              </div>
              <div className="text-[14.5px] text-fg-muted">{choice}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------
 * Close
 * ---------------------------------------------------------------------- */

function FinalCall() {
  return (
    <section className="relative overflow-hidden border-t border-hairline">
      <div className="aurora drift" aria-hidden />
      <div className="relative mx-auto max-w-3xl px-5 py-28 text-center">
        <h2 className="text-balance text-title font-semibold">
          Ask it for something, and watch what it{" "}
          <span className="text-lilac">refuses to do quietly</span>.
        </h2>
        <p className="mx-auto mt-5 max-w-lg text-pretty text-[15.5px] leading-relaxed text-fg-muted">
          The demo runs against a fake account, costs nothing, and needs no cloud
          credentials at all.
        </p>
        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <Link href="/build" className={buttonClass("primary", "lg")}>
            Open the app
            <Arrow />
          </Link>
          <a
            href="https://webr0bhza.z13.web.core.windows.net/"
            target="_blank"
            rel="noreferrer"
            className={buttonClass("normal", "lg")}
          >
            See a page it built
          </a>
        </div>
      </div>
    </section>
  );
}

function Arrow() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M3 8h10m0 0-4-4m4 4-4 4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
