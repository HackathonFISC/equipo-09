"use client";

import { Skeleton } from "@puente/ui/components/skeleton";
import { CalendarClock } from "lucide-react";
import { useEffect, useState } from "react";

import type { Application, ReviewTask } from "@/lib/api/client";
import { loadShortlists } from "@/lib/api/reviews";

const slotFmt = new Intl.DateTimeFormat("es-PA", {
	weekday: "short",
	day: "numeric",
	month: "short",
	hour: "2-digit",
	minute: "2-digit",
	timeZone: "America/Panama",
});

type Block = { postingId: string; title: string; applications: Application[] };
type State =
	| { status: "loading" }
	| { status: "error"; message: string }
	| { status: "ready"; blocks: Block[] };

type ProposalBlock = {
	postingId?: string;
	title?: string;
	candidates?: { youthId?: string; displayName?: string }[];
};

/**
 * Tras aprobar una lista corta: quién quedó enviado y a qué hora es su
 * entrevista (franjas de 30 min sin choques, hora de Panamá). Lee la BD real.
 */
export function ScheduledInterviews({ task }: { task: ReviewTask }) {
	const [state, setState] = useState<State>({ status: "loading" });
	const proposal = (task.proposal.postings ?? []) as ProposalBlock[];
	const names = new Map(
		proposal.flatMap((b) =>
			(b.candidates ?? []).map((c) => [c.youthId, c.displayName] as const),
		),
	);

	useEffect(() => {
		let live = true;
		const blocks = (task.proposal.postings ?? []) as ProposalBlock[];
		const ids = blocks.flatMap((b) => (b.postingId ? [b.postingId] : []));
		loadShortlists(ids).then((r) => {
			if (!live) return;
			if (!r.ok) {
				setState({ status: "error", message: r.message });
				return;
			}
			setState({
				status: "ready",
				blocks: r.data.map((d) => ({
					...d,
					title:
						blocks.find((b) => b.postingId === d.postingId)?.title ?? "Oferta",
				})),
			});
		});
		return () => {
			live = false;
		};
	}, [task.proposal]);

	if (state.status === "loading") {
		return <Skeleton className="h-16 w-full" />;
	}
	if (state.status === "error") {
		return (
			<p role="alert" className="text-danger-fg text-sm">
				No pudimos leer las entrevistas agendadas: {state.message}
			</p>
		);
	}
	const sent = state.blocks.filter((b) => b.applications.length > 0);
	if (sent.length === 0) {
		return (
			<p className="text-muted-foreground text-sm">
				No se envió ningún candidato, así que no hay entrevistas agendadas.
			</p>
		);
	}
	return (
		<section aria-labelledby="entrevistas" className="flex flex-col gap-2">
			<h4 id="entrevistas" className="flex items-center gap-2 font-medium">
				<CalendarClock className="size-4 text-success-fg" aria-hidden="true" />
				Entrevistas agendadas (hora de Panamá)
			</h4>
			<ul className="flex flex-col gap-2">
				{sent.map((b) => (
					<li key={b.postingId} className="border p-3">
						<p className="font-medium">{b.title}</p>
						<ul className="mt-1 flex flex-col gap-0.5">
							{b.applications.map((a) => {
								const slot = a.interviewSlots?.[0];
								return (
									<li
										key={a.id}
										className="flex flex-wrap justify-between gap-x-4"
									>
										<span>
											{names.get(a.matchResult.youthId) ?? "Candidato"}
										</span>
										<span className="tabular font-mono text-muted-foreground">
											{slot
												? slotFmt.format(new Date(slot.startsAt))
												: "sin franja"}
										</span>
									</li>
								);
							})}
						</ul>
					</li>
				))}
			</ul>
		</section>
	);
}
