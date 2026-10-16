"use client";

import { cn } from "@puente/ui/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { roles } from "@/lib/roles";

import { ModeToggle } from "./mode-toggle";

function BrandMark() {
	return (
		<svg
			viewBox="0 0 32 20"
			aria-hidden="true"
			className="h-5 w-8 text-primary"
		>
			<path
				d="M1 17h30M4 17V11M28 17V11M4 11C9 3 23 3 28 11M10 17V8.2M16 17V6.4M22 17V8.2"
				fill="none"
				stroke="currentColor"
				strokeWidth="2"
				strokeLinecap="square"
			/>
		</svg>
	);
}

export default function Header() {
	const pathname = usePathname();
	const isActive = (href: string) =>
		pathname === href || pathname.startsWith(`${href}/`);

	return (
		<header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur-sm supports-backdrop-filter:bg-background/80">
			<a
				href="#contenido"
				className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
			>
				Saltar al contenido
			</a>
			<div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
				<Link
					href="/"
					className="flex shrink-0 items-center gap-2 font-semibold text-base tracking-tight"
				>
					<BrandMark />
					Puente
				</Link>

				<nav
					aria-label="Roles"
					className="-mb-px hidden h-full items-stretch gap-1 md:flex"
				>
					{roles.map((role) => (
						<Link
							key={role.id}
							href={role.href}
							aria-current={isActive(role.href) ? "page" : undefined}
							className={cn(
								"flex items-center border-transparent border-b-2 px-3 text-muted-foreground text-sm transition-colors hover:text-foreground",
								"aria-[current=page]:border-primary aria-[current=page]:font-medium aria-[current=page]:text-foreground",
							)}
						>
							{role.label}
						</Link>
					))}
				</nav>

				<div className="ml-auto flex items-center gap-1">
					<Link
						href="/datos"
						aria-current={isActive("/datos") ? "page" : undefined}
						className="flex h-9 items-center px-3 text-muted-foreground text-sm hover:text-foreground aria-[current=page]:font-medium aria-[current=page]:text-foreground"
					>
						Datos semilla
					</Link>
					<ModeToggle />
				</div>
			</div>

			<nav aria-label="Roles" className="-mb-px grid grid-cols-4 md:hidden">
				{roles.map((role) => (
					<Link
						key={role.id}
						href={role.href}
						aria-current={isActive(role.href) ? "page" : undefined}
						className="flex h-11 items-center justify-center border-transparent border-b-2 text-muted-foreground text-sm aria-[current=page]:border-primary aria-[current=page]:font-medium aria-[current=page]:text-foreground"
					>
						{role.shortLabel}
					</Link>
				))}
			</nav>
		</header>
	);
}
