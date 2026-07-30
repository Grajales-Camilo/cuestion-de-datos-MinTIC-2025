import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LiveRegion } from "../../../components/ui/LiveRegion";
import { Skeleton } from "../../../components/ui/Skeleton";
import { VisuallyHidden } from "../../../components/ui/VisuallyHidden";
import { Card, CardHeader, CardBody, CardFooter } from "../../../components/ui/Card";

describe("LiveRegion", () => {
  it("role=status, aria-live=polite y aria-atomic=true por defecto", () => {
    render(<LiveRegion message="Investigación completada." />);
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveAttribute("aria-atomic", "true");
    expect(region).toHaveTextContent("Investigación completada.");
  });

  it("visualmente oculta por defecto (sr-only), pero presente en el DOM", () => {
    render(<LiveRegion message="Texto" />);
    expect(screen.getByRole("status").className).toMatch(/sr-only/);
  });

  it("sustituye el mensaje anterior en vez de acumular una lista (sin ruido repetitivo)", () => {
    const { rerender } = render(<LiveRegion message="Paso 1" />);
    expect(screen.getByRole("status")).toHaveTextContent("Paso 1");
    rerender(<LiveRegion message="Paso 2" />);
    const region = screen.getByRole("status");
    expect(region).toHaveTextContent("Paso 2");
    expect(region).not.toHaveTextContent("Paso 1");
  });
});

describe("Skeleton", () => {
  it("es aria-hidden: un lector de pantalla no debe anunciar cada bloque decorativo", () => {
    const { container } = render(<Skeleton className="h-4 w-32" />);
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });

  it("usa un pulso suave (animate-pulse), sin shimmer ni degradado", () => {
    const { container } = render(<Skeleton />);
    expect(container.firstChild.className).toMatch(/animate-pulse/);
    expect(container.firstChild.className).not.toMatch(/gradient/);
  });
});

describe("VisuallyHidden", () => {
  it("el contenido sigue accesible por texto aunque esté oculto visualmente", () => {
    render(
      <button type="button">
        Ver evidencia
        <VisuallyHidden> de la deserción escolar en Antioquia</VisuallyHidden>
      </button>
    );
    expect(
      screen.getByRole("button", { name: "Ver evidencia de la deserción escolar en Antioquia" })
    ).toBeInTheDocument();
  });
});

describe("Card", () => {
  it("compone Header/Body/Footer sin sombra dura (solo borde)", () => {
    render(
      <Card data-testid="card">
        <CardHeader>Encabezado</CardHeader>
        <CardBody>Cuerpo</CardBody>
        <CardFooter>Pie</CardFooter>
      </Card>
    );
    const card = screen.getByTestId("card");
    expect(card.className).toMatch(/border border-cdt-blue-100/);
    expect(card.className).not.toMatch(/shadow/);
    expect(screen.getByText("Encabezado")).toBeInTheDocument();
    expect(screen.getByText("Cuerpo")).toBeInTheDocument();
    expect(screen.getByText("Pie")).toBeInTheDocument();
  });
});
