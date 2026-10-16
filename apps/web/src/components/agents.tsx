import { cn } from "@puente/ui/lib/utils";
import {
	BriefcaseBusiness,
	Calculator,
	GraduationCap,
	type LucideIcon,
	MessagesSquare,
	Route,
	Scale,
	Send,
	UserCheck,
	UserRoundSearch,
} from "lucide-react";

import type { AgentName, AgentTrace } from "@/lib/api/client";

/** Nombre, ícono y color de cada agente (docs/04 §4). Se reutiliza en la traza. */
export const agentMeta: Record<
	AgentName,
	{ label: string; icon: LucideIcon; text: string; border: string }
> = {
	supervisor: {
		label: "Supervisor",
		icon: Route,
		text: "text-foreground",
		border: "border-foreground/30",
	},
	mercado: {
		label: "Mercado",
		icon: BriefcaseBusiness,
		text: "text-agent-mercado",
		border: "border-agent-mercado/50",
	},
	perfil: {
		label: "Perfil",
		icon: UserRoundSearch,
		text: "text-agent-perfil",
		border: "border-agent-perfil/50",
	},
	matching: {
		label: "Matching",
		icon: Calculator,
		text: "text-agent-matching",
		border: "border-agent-matching/50",
	},
	formacion: {
		label: "Formación",
		icon: GraduationCap,
		text: "text-agent-formacion",
		border: "border-agent-formacion/50",
	},
	postulacion: {
		label: "Postulación",
		icon: Send,
		text: "text-agent-postulacion",
		border: "border-agent-postulacion/50",
	},
	entrevista: {
		label: "Entrevista",
		icon: MessagesSquare,
		text: "text-agent-perfil",
		border: "border-agent-perfil/50",
	},
	auditor: {
		label: "Auditor",
		icon: Scale,
		text: "text-warning-fg",
		border: "border-agent-auditor/60",
	},
	orientador: {
		label: "Orientador",
		icon: UserCheck,
		text: "text-agent-orientador dark:text-foreground",
		border: "border-agent-orientador/50",
	},
};

export function AgentBadge({
	agent,
	className,
}: {
	agent: AgentName;
	className?: string;
}) {
	const { label, icon: Icon, text, border } = agentMeta[agent];
	return (
		<span
			className={cn(
				"inline-flex items-center gap-1.5 border px-2 py-0.5 font-medium text-foreground text-xs",
				border,
				className,
			)}
		>
			<Icon className={cn("size-3.5", text)} aria-hidden="true" />
			{label}
		</span>
	);
}

/** Estado "procesando": siempre nombra al agente que trabaja. */
export function AgentWorking({
	agent,
	children,
}: {
	agent: AgentName;
	children: React.ReactNode;
}) {
	const { icon: Icon, text } = agentMeta[agent];
	return (
		<output
			aria-live="polite"
			className="flex items-center gap-3 border border-dashed px-4 py-3 text-sm"
		>
			<Icon
				className={cn("size-5 shrink-0 animate-pulse", text)}
				aria-hidden="true"
			/>
			<span>{children}</span>
		</output>
	);
}

/** Pasos del grafo: qué decidió cada agente y por qué. */
export function TraceSteps({
	steps,
	title = "Cómo se decidió",
}: {
	steps: AgentTrace[];
	title?: string;
}) {
	const sorted = [...steps].sort((a, b) => a.step - b.step);
	return (
		<section aria-label={title} className="flex flex-col gap-3">
			<h3 className="font-medium text-sm">{title}</h3>
			<ol className="flex flex-col">
				{sorted.map((s) => {
					const hitl = s.agent === "orientador";
					return (
						<li
							key={`${s.step}-${s.agent}`}
							className={cn(
								"relative flex flex-col gap-1 border-l-2 py-2 pl-4",
								hitl ? "border-warning" : agentMeta[s.agent].border,
							)}
						>
							<span className="flex flex-wrap items-center gap-2">
								<AgentBadge agent={s.agent} />
								{s.durationMs != null ? (
									<span className="tabular font-mono text-muted-foreground text-xs">
										{(s.durationMs / 1000).toFixed(1)} s
									</span>
								) : null}
							</span>
							<span className="font-medium text-sm">{s.decision}</span>
							{s.reason ? (
								<span className="text-pretty text-muted-foreground text-sm">
									{s.reason}
								</span>
							) : null}
						</li>
					);
				})}
			</ol>
		</section>
	);
}
