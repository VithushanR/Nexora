import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

type PlanName = "free" | "pro" | "team";
type BillingCycle = "monthly" | "annual";

interface Plan {
  name: PlanName;
  label: string;
  summary: string;
  monthlyPrice: number;
  annualMonthlyPrice: number;
  capacity: Array<{ value: string; label: string }>;
  features: string[];
  accent: "quiet" | "violet" | "ink";
}

const SELECTED_PLAN_KEY = "nexora_selected_plan";

const PLANS: Plan[] = [
  {
    name: "free",
    label: "Free",
    summary: "A clear starting point for focused literature reviews.",
    monthlyPrice: 0,
    annualMonthlyPrice: 0,
    capacity: [
      { value: "3", label: "research runs / month" },
      { value: "50", label: "candidates / run" },
      { value: "2", label: "synthesis workers" },
    ],
    features: [
      "arXiv full text with labelled abstract fallback",
      "Report-grounded Copilot",
      "Reduced but honest gap discovery",
      "Markdown report export",
    ],
    accent: "quiet",
  },
  {
    name: "pro",
    label: "Pro",
    summary: "Deeper evidence coverage for regular research work.",
    monthlyPrice: 19,
    annualMonthlyPrice: 15,
    capacity: [
      { value: "50", label: "research runs / month" },
      { value: "150", label: "candidates / run" },
      { value: "7", label: "full-text strategies" },
    ],
    features: [
      "Complete open-access full-text cascade",
      "Live web search in Copilot",
      "Writing assistant",
      "Expanded document uploads",
      "Branded PDF report export",
      "20 contradiction pairs per review",
    ],
    accent: "violet",
  },
  {
    name: "team",
    label: "Team",
    summary: "Maximum throughput for demanding research programmes.",
    monthlyPrice: 49,
    annualMonthlyPrice: 39,
    capacity: [
      { value: "∞", label: "research runs" },
      { value: "300", label: "candidates / run" },
      { value: "8", label: "synthesis workers" },
    ],
    features: [
      "Everything in Pro",
      "Highest screening and synthesis concurrency",
      "40 contradiction pairs per review",
      "Largest document allowance",
      "Full-depth gap discovery",
      "20 concurrent screening workers",
    ],
    accent: "ink",
  },
];

function loadSelectedPlan(): PlanName | null {
  try {
    const value = localStorage.getItem(SELECTED_PLAN_KEY);
    return value === "free" || value === "pro" || value === "team" ? value : null;
  } catch {
    return null;
  }
}

function CheckIcon() {
  return (
    <svg className="mt-0.5 shrink-0 text-violet-600 dark:text-violet-400" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

export default function PlansPage() {
  const { user } = useAuth();
  const currentPlan = user?.tier ?? "free";
  const [billingCycle, setBillingCycle] = useState<BillingCycle>("annual");
  const [selectedPlan, setSelectedPlan] = useState<PlanName | null>(loadSelectedPlan);

  function selectPlan(plan: PlanName) {
    setSelectedPlan(plan);
    try {
      localStorage.setItem(SELECTED_PLAN_KEY, plan);
    } catch {
      // Selection still works for this page when browser storage is unavailable.
    }
  }

  return (
    <div className="thin-scroll h-full overflow-y-auto bg-slate-50 dark:bg-slate-950">
      <div className="mx-auto w-full max-w-[1180px] px-5 pb-16 pt-20 sm:px-8 lg:px-10 lg:pt-14">
        <div className="mb-9 flex flex-col gap-6 border-b border-slate-200 pb-8 dark:border-slate-800 md:flex-row md:items-end md:justify-between">
          <div>
            <Link
              to="/"
              className="mb-5 inline-flex items-center gap-2 text-sm font-medium text-slate-500 transition hover:text-violet-700 focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 dark:text-slate-400 dark:hover:text-violet-300"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Return to workspace
            </Link>
            <h1 className="max-w-2xl text-3xl font-semibold tracking-[-0.035em] text-slate-950 dark:text-white sm:text-4xl">
              Choose how deeply Nexora researches
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-400 sm:text-base">
              Every plan keeps evidence traceable. Higher tiers expand the papers, full-text sources, and analysis capacity available to each review.
            </p>
          </div>

          <div className="inline-flex w-fit rounded-xl border border-slate-200 bg-white p-1 shadow-sm dark:border-slate-700 dark:bg-slate-900" aria-label="Billing cycle">
            {(["monthly", "annual"] as const).map((cycle) => (
              <button
                key={cycle}
                type="button"
                onClick={() => setBillingCycle(cycle)}
                aria-pressed={billingCycle === cycle}
                className={`rounded-lg px-4 py-2 text-xs font-semibold capitalize transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 ${
                  billingCycle === cycle
                    ? "bg-slate-900 text-white dark:bg-violet-500"
                    : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
                }`}
              >
                {cycle}
                {cycle === "annual" && <span className="ml-1.5 text-[10px] text-emerald-500">save 20%</span>}
              </button>
            ))}
          </div>
        </div>

        {selectedPlan && selectedPlan !== currentPlan && (
          <div role="status" className="mb-6 flex items-start gap-3 rounded-xl border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-900 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-200">
            <svg className="mt-0.5 shrink-0" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 8v4M12 16h.01" />
            </svg>
            <p>
              <span className="font-semibold capitalize">{selectedPlan} selected.</span>{" "}
              Billing is not connected yet, so your backend-enforced {currentPlan} plan has not changed.
            </p>
          </div>
        )}

        <div className="grid gap-5 lg:grid-cols-3">
          {PLANS.map((plan) => {
            const isCurrent = currentPlan === plan.name;
            const isSelected = selectedPlan === plan.name && !isCurrent;
            const price = billingCycle === "annual" ? plan.annualMonthlyPrice : plan.monthlyPrice;
            const buttonClass =
              plan.accent === "violet"
                ? "bg-violet-600 text-white hover:bg-violet-500"
                : plan.accent === "ink"
                  ? "bg-slate-900 text-white hover:bg-slate-800 dark:bg-white dark:text-slate-950 dark:hover:bg-slate-200"
                  : "border border-slate-300 bg-white text-slate-800 hover:border-violet-300 hover:text-violet-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200";

            return (
              <article
                key={plan.name}
                className={`relative flex min-h-[610px] flex-col overflow-hidden rounded-2xl border bg-white dark:bg-slate-900 ${
                  plan.accent === "violet"
                    ? "border-violet-400 shadow-[0_18px_50px_-30px_rgba(124,58,237,0.7)] dark:border-violet-600"
                    : "border-slate-200 dark:border-slate-800"
                }`}
              >
                {plan.accent === "violet" && (
                  <div className="bg-violet-600 px-5 py-2 text-center text-xs font-semibold text-white">
                    Best for independent researchers
                  </div>
                )}

                <div className="flex flex-1 flex-col p-6">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-xl font-semibold text-slate-950 dark:text-white">{plan.label}</h2>
                      <p className="mt-2 min-h-10 text-sm leading-5 text-slate-500 dark:text-slate-400">{plan.summary}</p>
                    </div>
                    {isCurrent && (
                      <span className="shrink-0 rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                        Current plan
                      </span>
                    )}
                  </div>

                  <div className="mt-7 flex items-end gap-2 border-b border-slate-100 pb-6 dark:border-slate-800">
                    <span className="pb-1 text-lg text-slate-500">$</span>
                    <span className="text-5xl font-semibold tracking-[-0.055em] text-slate-950 dark:text-white">{price}</span>
                    <span className="pb-1 text-xs leading-4 text-slate-500">
                      USD / month{plan.name === "team" ? " / member" : ""}
                    </span>
                  </div>
                  {billingCycle === "annual" && price > 0 && (
                    <p className="mt-2 text-xs text-slate-400">Billed annually at ${price * 12}.</p>
                  )}

                  <div className="my-6 grid grid-cols-3 divide-x divide-slate-200 rounded-xl bg-slate-50 px-2 py-4 dark:divide-slate-700 dark:bg-slate-800/70">
                    {plan.capacity.map((item) => (
                      <div key={item.label} className="px-2 text-center">
                        <p className="text-lg font-semibold text-slate-900 dark:text-white">{item.value}</p>
                        <p className="mt-1 text-[10px] leading-3 text-slate-500 dark:text-slate-400">{item.label}</p>
                      </div>
                    ))}
                  </div>

                  <button
                    type="button"
                    disabled={isCurrent}
                    onClick={() => selectPlan(plan.name)}
                    className={`w-full rounded-xl px-4 py-3 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2 disabled:cursor-default disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400 dark:disabled:border-slate-700 dark:disabled:bg-slate-800 dark:disabled:text-slate-500 ${buttonClass}`}
                  >
                    {isCurrent ? "Your current plan" : isSelected ? `${plan.label} selected` : `Select ${plan.label}`}
                  </button>

                  <ul className="mt-7 space-y-3">
                    {plan.features.map((feature) => (
                      <li key={feature} className="flex gap-2.5 text-sm leading-5 text-slate-600 dark:text-slate-300">
                        <CheckIcon />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </article>
            );
          })}
        </div>

        <p className="mx-auto mt-8 max-w-2xl text-center text-xs leading-5 text-slate-500 dark:text-slate-400">
          Prices are shown in USD. Plan selection is saved in this browser; billing and server-side tier activation require the payment integration.
        </p>
      </div>
    </div>
  );
}
