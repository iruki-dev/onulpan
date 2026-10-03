import { notFound } from "next/navigation";
import { EditionView } from "@/components/EditionView";
import { Tracker } from "@/components/Tracker";
import { editionById } from "@/lib/editions";
import { requireUser } from "@/lib/session";

export default async function PastEditionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const user = await requireUser(`/e/${id}`);
  const ed = Number.isInteger(Number(id)) ? await editionById(Number(id), user.id) : null;
  if (!ed) notFound();
  return (
    <>
      <Tracker page="past_edition" editionId={ed.id} />
      <EditionView date={ed.edition_date} slots={ed.slots} editionId={ed.id} />
    </>
  );
}
