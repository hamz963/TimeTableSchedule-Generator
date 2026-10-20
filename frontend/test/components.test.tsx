import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SolverStatus from "@/components/SolverStatus";
import TimetableGrid from "@/components/TimetableGrid";

const assignments = [
  { course_id: 11, faculty_id: 2, venue_id: 1, slot_id: 3 },
  { course_id: 12, faculty_id: 2, venue_id: 2, slot_id: 3 },
];

const names = {
  courses: { 11: "Data Structures", 12: "Algorithms" },
  teachers: { 2: "Dr. Ahmad" },
  rooms: { 1: "Lab A", 2: "Room B" },
  slots: { 3: "Mon 09:00–10:00" },
};

describe("TimetableGrid", () => {
  it("shows an empty state instead of an empty table", () => {
    render(<TimetableGrid assignments={[]} />);
    expect(screen.getByText(/no assignments yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders course and teacher names in the matching slot/venue cell", () => {
    render(<TimetableGrid assignments={assignments} names={names} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Data Structures")).toBeInTheDocument();
    expect(screen.getByText("Algorithms")).toBeInTheDocument();
    expect(screen.getAllByText("Dr. Ahmad")).toHaveLength(2);
    expect(screen.getByText("Mon 09:00–10:00")).toBeInTheDocument();
    // Rooms are column headers, one per distinct venue.
    expect(screen.getByRole("columnheader", { name: "Lab A" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Room B" })).toBeInTheDocument();
  });

  it("falls back to id-based labels when names are missing", () => {
    render(<TimetableGrid assignments={[assignments[0]]} />);
    expect(screen.getByText("Course 11")).toBeInTheDocument();
    expect(screen.getByText("Faculty 2")).toBeInTheDocument();
  });
});

describe("SolverStatus", () => {
  it("renders nothing without a status", () => {
    const { container } = render(<SolverStatus loading={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("announces a running solver", () => {
    render(<SolverStatus loading status="optimal" />);
    expect(screen.getByText(/solver running/i)).toBeInTheDocument();
  });

  it("marks feasible and infeasible results differently", () => {
    const { rerender } = render(<SolverStatus loading={false} status="feasible" />);
    expect(screen.getByText(/solver status/i)).toHaveClass("border-green-300");
    rerender(<SolverStatus loading={false} status="infeasible" />);
    expect(screen.getByText(/solver status/i)).toHaveClass("border-red-300");
  });
});
