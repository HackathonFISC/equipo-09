"use client";

import { Button } from "@puente/ui/components/button";
import { Play } from "lucide-react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AgentWorking } from "@/components/agents";
import { runMatching } from "@/lib/api/reviews";

/**
 * Dispara una corrida de matching (doc 03 §2: «Ejecutar matching») y lleva a su
 * traza, donde se ve Matching → Auditor → Postulación y la pausa del orientador.
 */
export function MatchRunButton() {
	const router = useRouter();
	const [running, setRunning] = useState(false);
	const [error, setError] = useState<string | null>(null);

	async function run() {
		setRunning(true);
		setError(null);
		const r = await runMatching();
		if (r.ok) {
			router.push(`/traza/${encodeURIComponent(r.data.threadId)}` as Route);
			return;
		}
		setError(r.message);
		setRunning(false);
	}

	if (running) {
		return (
			<AgentWorking agent="matching">
				Matching, Auditor y Postulación están trabajando…
			</AgentWorking>
		);
	}
	return (
		<div className="flex flex-col items-start gap-1 sm:items-end">
			<Button size="lg" className="h-11" onClick={() => void run()}>
				<Play aria-hidden="true" />
				Ejecutar matching
			</Button>
			{error ? (
				<p role="alert" className="max-w-xs text-danger-fg text-sm">
					{error}
				</p>
			) : null}
		</div>
	);
}
