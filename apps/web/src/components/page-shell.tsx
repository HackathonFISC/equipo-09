import { cn } from "@puente/ui/lib/utils";

/** Encabezado común de las rutas por rol; el rol activo ya se marca en la navegación. */
export function RoleHeader({
	title,
	description,
	actions,
}: {
	title: string;
	description: React.ReactNode;
	actions?: React.ReactNode;
}) {
	return (
		<div className="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
			<div className="flex max-w-2xl flex-col gap-2">
				<h1 className="text-balance font-semibold text-2xl tracking-tight sm:text-3xl">
					{title}
				</h1>
				<p className="text-pretty text-muted-foreground">{description}</p>
			</div>
			{actions ? (
				<div className="flex shrink-0 flex-wrap items-start gap-2">
					{actions}
				</div>
			) : null}
		</div>
	);
}

export function PageShell({
	width = "wide",
	className,
	children,
}: {
	width?: "narrow" | "wide";
	className?: string;
	children: React.ReactNode;
}) {
	return (
		<main
			id="contenido"
			className={cn(
				"mx-auto flex w-full flex-col gap-8 px-4 py-8 sm:py-10",
				width === "narrow" ? "max-w-xl" : "max-w-6xl",
				className,
			)}
		>
			{children}
		</main>
	);
}
