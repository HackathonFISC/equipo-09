import { cn } from "@puente/ui/lib/utils";
import { CircleCheck, FlaskConical, TriangleAlert } from "lucide-react";

import type { DataSource } from "@/lib/api/catalog";

import { RetryButton } from "./retry-button";

/** Dice de dónde vienen los datos: nunca se presentan datos de ejemplo como reales. */
export function DataSourceNote({
	source,
	reason,
	className,
}: {
	source: DataSource;
	reason?: string;
	className?: string;
}) {
	if (source === "api") {
		return (
			<p
				className={cn(
					"flex items-center gap-1.5 text-sm text-success-fg",
					className,
				)}
			>
				<CircleCheck className="size-4 shrink-0" aria-hidden="true" />
				Datos de la API
			</p>
		);
	}
	return (
		<p
			className={cn(
				"flex items-start gap-1.5 border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning-fg",
				className,
			)}
		>
			<FlaskConical className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
			<span>
				<span className="font-medium">Datos de ejemplo.</span> {reason}
			</span>
		</p>
	);
}

export function ErrorState({
	title,
	message,
}: {
	title: string;
	message: string;
}) {
	return (
		<div
			role="alert"
			className="flex flex-col items-start gap-3 border border-danger/40 bg-danger/5 p-6"
		>
			<p className="flex items-center gap-2 font-medium text-danger-fg">
				<TriangleAlert className="size-5 shrink-0" aria-hidden="true" />
				{title}
			</p>
			<p className="text-muted-foreground text-sm">
				{message} Revisa que la API esté corriendo e inténtalo de nuevo.
			</p>
			<RetryButton />
		</div>
	);
}
