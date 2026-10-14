"use client";
import { useRouter } from "next/navigation";
import ConstraintForm from "@/components/ConstraintForm";

export default function CreateConstraint() {
  const router = useRouter();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Create Constraint</h1>
      <ConstraintForm onCreated={() => router.push("/constraints")} />
    </div>
  );
}
