"use client";

import { Button } from "@puente/ui/components/button";
import { Skeleton } from "@puente/ui/components/skeleton";
import { cn } from "@puente/ui/lib/utils";
import { ChevronRight, Inbox, RotateCw, TriangleAlert } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { agentMeta } from "@/components/agents";
import { DataSourceNote } from "@/components/data-states";
import { TraceStatusBadge } from "@/components/trace-timeline";
import type { AgentName, TraceSummary } from "@/lib/api/client";
import { loadTraces } from "@/lib/api/traces";
import { plural } from "@/lib/format";

const when = new Intl.DateTimeFormat("es-PA", {
	day: "numeric",
	month: "short",
	hour: "2-digit",
	minute: "2-digit",
});

type State =
	| { status: "loading" }
	| { status: "error"; message: string }
	| {
			status: "ready";
			traces: TraceSummary[];
			source: "api" | "mock";
			reason?: string;
	  };

function agentLabel(name: string) {
	return name in agentMeta ? agentMeta[name as AgentName].label : name;
}

export function TraceList() {
	const [state, setState] = useState<State>({ status: "loading" });

	const load = useCallback(async () => {
		setState({ status: "loading" });
		const r = await loadTraces();
		setState(
			r.ok
				? {
						status: "ready",
						traces: r.data,
						source: r.source,
						reason: r.reason,
					}
				: { status: "error", message: r.message },
		);
	}, []);

	useEffect(() => {
		void load();
	}, [load]);

	if (state.status === "loading") {
		return (
			<div className="flex flex-col border-y">
				<output aria-live="polite" className="sr-only">
					Cargando las corridas recientes…
				</output>
				{["a", "b", "c", "d"].map((k) => (
					<div
						key={k}
						className="flex flex-col gap-3 border-b py-5 last:border-b-0"
					>
						<Skeleton className="h-6 w-40" />
						<Skeleton className="h-5 w-3/4" />
						<Skeleton className="h-4 w-1/2" />
					</div>
				))}
			</div>
		);
	}

	if (state.status === "error") {
		return (
			<div className="flex flex-col items-start gap-3">
				<div
					role="alert"
					className="flex flex-col gap-1 border border-danger/40 bg-danger/5 p-4 text-sm"
				>
					<p className="flex items-center gap-2 font-medium text-danger-fg">
						<TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
						No pudimos cargar las corridas
					</p>
					<p>{state.message}</p>
				</div>
				<Button
					variant="outline"
					size="lg"
					className="h-11"
					onClick={() => void load()}
				>
					<RotateCw aria-hidden="true" />
					Reintentar
				</Button>
			</div>
		);
	}

	if (state.traces.length === 0) {
		return (
			<div className="flex flex-col items-center gap-3 border border-dashed px-6 py-12 text-center">
				<Inbox className="size-8 text-muted-foreground" aria-hidden="true" />
				<p className="font-medium">Todavía no hay corridas</p>
				<p className="max-w-sm text-muted-foreground text-sm">
					Cuando un joven, una empresa o un centro active a los agentes, su
					recorrido aparecerá aquí con cada decisión explicada.
				</p>
			</div>
		);
	}

	return (
		<div className="flex flex-col gap-4">
			<DataSourceNote source={state.source} reason={state.reason} />
			<ul className="flex flex-col border-y">
				{state.traces.map((t) => (
					<li key={t.threadId} className="border-b last:border-b-0">
						<Link
							href={`/traza/${encodeURIComponent(t.threadId)}` as Route}
							className={cn(
								"group flex items-start gap-3 py-5 outline-none",
								"focus-visible:ring-2 focus-visible:ring-ring/50",
							)}
						>
							<span className="flex min-w-0 flex-1 flex-col gap-2">
								<span className="flex flex-wrap items-center gap-x-3 gap-y-2">
									<TraceStatusBadge status={t.status} />
									<span className="tabular text-muted-foreground text-sm">
										<time dateTime={t.lastActivityAt}>
											{when.format(new Date(t.lastActivityAt))}
										</time>
										{" · "}
										{plural(t.stepCount, "paso", "pasos")}
									</span>
								</span>
								{t.lastDecision ? (
									<span className="text-pretty font-medium leading-snug">
										{t.lastDecision}
									</span>
								) : null}
								<span className="text-muted-foreground text-sm">
									{t.agents.map(agentLabel).join(" → ")}
								</span>
								<span className="break-all font-mono text-muted-foreground text-xs">
									{t.threadId}
								</span>
							</span>
							<span className="flex min-h-11 items-center gap-1 text-primary text-sm underline-offset-4 group-hover:underline">
								<span className="max-sm:sr-only">Ver traza</span>
								<ChevronRight className="size-4" aria-hidden="true" />
							</span>
						</Link>
					</li>
				))}
			</ul>
		</div>
	);
}
