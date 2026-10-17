"use client";

import { Button } from "@puente/ui/components/button";
import { Skeleton } from "@puente/ui/components/skeleton";
import { GraduationCap, RotateCw, SearchX, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { DataSourceNote } from "@/components/data-states";
import { OpportunityCard } from "@/components/opportunity-card";
import { TraceLink } from "@/components/trace-link";
import { loadOpportunities, type Opportunity } from "@/lib/api/reviews";
import { loadRunThread } from "@/lib/api/traces";
import { plural } from "@/lib/format";
import { rememberYouth } from "@/lib/youth-session";

type State =
	| { status: "loading" }
	| { status: "error"; message: string }
	| {
			status: "ready";
			items: Opportunity[];
			source: "api" | "mock";
			reason?: string;
			/** Hilo del grafo que produjo estas ofertas, para enlazar su traza. */
			threadId: string | null;
	  };

/** Motivo humano por el que una oferta no se le muestra al joven. */
function discardReason(o: Opportunity): string {
	const { constraintsChecked: c } = o.match;
	const reasons = [
		c.commuteMin > 90 ? `más de 90 min de viaje (${c.commuteMin} min)` : null,
		c.scheduleOverlap ? null : "el horario no coincide con el tuyo",
		c.salaryOk ? null : "el salario queda bajo tu mínimo",
	].filter(Boolean);
	return reasons.length > 0 ? reasons.join(" y ") : "no cumple tus condiciones";
}

export function OpportunityList({ youthId }: { youthId: string }) {
	const [state, setState] = useState<State>({ status: "loading" });

	const load = useCallback(async () => {
		setState({ status: "loading" });
		const r = await loadOpportunities(youthId);
		if (!r.ok) {
			setState({ status: "error", message: r.message });
			return;
		}
		rememberYouth(youthId);
		const runId = r.data[0]?.match.runId;
		const threadId = runId
			? await loadRunThread(runId, r.source === "mock")
			: null;
		setState({
			status: "ready",
			items: r.data,
			source: r.source,
			reason: r.reason,
			threadId,
		});
	}, [youthId]);

	useEffect(() => {
		void load();
	}, [load]);

	if (state.status === "loading") {
		return (
			<div className="flex flex-col gap-4">
				<output aria-live="polite" className="sr-only">
					Matching está buscando tus oportunidades…
				</output>
				{["a", "b"].map((k) => (
					<div key={k} className="flex flex-col gap-3 border p-4">
						<Skeleton className="h-6 w-3/4" />
						<Skeleton className="h-8 w-full" />
						<Skeleton className="h-16 w-full" />
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
						No pudimos cargar tus oportunidades
					</p>
					<p>{state.message}</p>
				</div>
				<Button variant="outline" size="lg" className="h-11" onClick={load}>
					<RotateCw aria-hidden="true" />
					Reintentar
				</Button>
			</div>
		);
	}

	const shown = state.items
		.filter((o) => o.match.status !== "rechazado")
		.sort((a, b) => b.match.score - a.match.score);
	const discarded = state.items.filter((o) => o.match.status === "rechazado");

	return (
		<div className="flex flex-col gap-6">
			<DataSourceNote source={state.source} reason={state.reason} />

			{shown.length === 0 ? (
				<div className="flex flex-col items-center gap-3 border border-dashed px-6 py-12 text-center">
					<SearchX
						className="size-8 text-muted-foreground"
						aria-hidden="true"
					/>
					<p className="font-medium">Todavía no hay ofertas para ti</p>
					<p className="max-w-xs text-muted-foreground text-sm">
						{discarded.length > 0
							? "Las que encontramos no se ajustan a tu viaje, horario o salario. Cuando entren ofertas nuevas, Matching vuelve a buscar."
							: "Cuando haya una oferta que te quede cerca y encaje con tus habilidades, aparecerá aquí con la explicación."}
					</p>
					<Link
						href={`/joven/perfil?id=${youthId}` as never}
						className="min-h-11 content-center text-primary text-sm underline underline-offset-4"
					>
						Completar mi perfil
					</Link>
				</div>
			) : (
				<section aria-labelledby="ofertas" className="flex flex-col gap-3">
					<h2 id="ofertas" className="font-medium text-sm">
						{plural(
							shown.length,
							"oferta a tu alcance",
							"ofertas a tu alcance",
						)}
					</h2>
					<ul className="flex flex-col gap-4">
						{shown.map((o) => (
							<OpportunityCard key={o.match.postingId} opportunity={o} />
						))}
					</ul>
				</section>
			)}

			<nav
				aria-label="Más sobre tus resultados"
				className="flex flex-col border-y sm:flex-row sm:gap-6"
			>
				<Link
					href={`/joven/formacion?id=${youthId}` as never}
					className="inline-flex min-h-11 items-center gap-2 text-primary text-sm underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
				>
					<GraduationCap className="size-4 shrink-0" aria-hidden="true" />
					Ver mi ruta de formación
				</Link>
				{state.threadId ? (
					<TraceLink threadId={state.threadId}>
						Ver cómo decidieron los agentes
					</TraceLink>
				) : null}
			</nav>

			{discarded.length > 0 ? (
				<details className="border p-4">
					<summary className="min-h-11 cursor-pointer content-center font-medium text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
						{plural(
							discarded.length,
							"oferta descartada",
							"ofertas descartadas",
						)}{" "}
						para ti
					</summary>
					<ul className="flex flex-col gap-2 pt-2 text-sm">
						{discarded.map((o) => (
							<li key={o.match.postingId}>
								<strong className="font-medium">
									{o.posting?.title ?? "Oferta"}
								</strong>
								: {discardReason(o)}.
							</li>
						))}
					</ul>
				</details>
			) : null}
		</div>
	);
}
