import { cn } from "@puente/ui/lib/utils";
import { Waypoints } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";

/** Enlace a la línea de tiempo de un hilo del grafo (/traza/[threadId]). */
export function TraceLink({
	threadId,
	children = "Ver la traza completa",
	className,
}: {
	threadId: string;
	children?: React.ReactNode;
	className?: string;
}) {
	return (
		<Link
			href={`/traza/${encodeURIComponent(threadId)}` as Route}
			className={cn(
				"inline-flex min-h-11 items-center gap-2 text-primary text-sm underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
				className,
			)}
		>
			<Waypoints className="size-4 shrink-0" aria-hidden="true" />
			{children}
		</Link>
	);
}
