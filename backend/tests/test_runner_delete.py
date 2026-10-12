from types import SimpleNamespace

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings
from app.models.tables import Document, Patient
from app.pipeline import extract, runner


def test_deleting_a_document_while_it_is_processed_stops_the_pipeline(tmp_path, monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(runner, "engine", eng)
    monkeypatch.setattr(get_settings(), "storage_dir", tmp_path)
    with Session(eng) as db:
        p = Patient(name="Asha Rao")
        db.add(p)
        db.commit()
        doc = Document(patient_id=p.id, filename="rx.jpg", mime_type="image/jpeg", file_path=str(tmp_path / "rx.jpg"))
        db.add(doc)
        db.commit()
        doc_id = doc.id

    def prepare(path, mime, pages_dir):
        pages_dir.mkdir(parents=True)
        with Session(eng) as other:  # the user deletes it from the upload list meanwhile
            other.delete(other.get(Document, doc_id))
            other.commit()
        return SimpleNamespace(pages=[], has_text_layer=False, notes=[])

    def never(*a, **k):
        raise AssertionError("the pipeline kept going after the document was deleted")

    monkeypatch.setattr(runner, "prepare", prepare)
    monkeypatch.setattr(extract, "classify", never)
    runner.process_document(doc_id)
    with Session(eng) as db:
        assert db.get(Document, doc_id) is None  # not re-created by the final save
    assert not (tmp_path / doc_id).exists()
