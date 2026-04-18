"""PDF generation Celery task — renders WeasyPrint report."""
import os
from datetime import datetime, timezone

try:
    from app.tasks.orchestrator import celery_app
except ImportError:
    from celery import Celery
    celery_app = Celery("skybase", broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"))


@celery_app.task(name="pipeline.pdf", bind=True, max_retries=2)
def generate_report_pdf(self, analysis_id: str):
    """Generate the PDF report for a completed analysis."""
    from app.db.base import SessionLocal
    from app.models.analysis import Analysis

    db = SessionLocal()
    try:
        from app.services.pdf_generator import generate_report

        pdf_path = generate_report(analysis_id, db)

        analysis = db.query(Analysis).filter_by(id=analysis_id).first()
        if analysis:
            analysis.report_url = f"/api/v1/analyses/{analysis_id}/report"
            analysis.report_s3_key = pdf_path
            db.commit()

        print(f"[PDF] Report generated: {pdf_path}")
        return {"status": "completed", "analysis_id": analysis_id, "path": pdf_path}

    except Exception as exc:
        print(f"[PDF] Error generating report for {analysis_id}: {exc}")
        try:
            self.retry(countdown=10, exc=exc)
        except self.MaxRetriesExceededError:
            return {"status": "failed", "analysis_id": analysis_id, "error": str(exc)}
    finally:
        db.close()
