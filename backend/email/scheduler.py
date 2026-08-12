import asyncio
import logging
from datetime import datetime
from backend.db import db
from backend.email.gmail_service import sync_user_gmail

logger = logging.getLogger("scheduler")
_scheduler_task = None
_running = False

async def run_sync_cycle():
    """Execute sync loop for all connected Gmail accounts."""
    logger.info("Starting background Gmail sync cycle...")
    start_time = datetime.utcnow()
    total_processed = 0
    
    try:
        # Fetch all linked Gmail accounts from Supabase
        accounts = db.get_gmail_accounts()
        logger.info(f"Loaded {len(accounts)} Gmail accounts to synchronize.")
        
        # Track synced emails count
        for account in accounts:
            user_id = account["user_id"]
            email = account["email"]
            try:
                logger.info(f"Syncing account: {email} for user {user_id}")
                res = sync_user_gmail(user_id)
                count = res[0] if isinstance(res, tuple) else (res or 0)
                total_processed += count
            except Exception as e:
                logger.error(f"Failed to sync Gmail account {email}: {e}")
                
        logger.info(f"Gmail sync cycle completed. Processed {total_processed} new opportunities.")
        
        try:
            db.log_automation_run(
                job_name="gmail_sync_job",
                status="COMPLETED",
                records_processed=total_processed
            )
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error during background scheduler run: {e}")
        try:
            db.log_automation_run(
                job_name="gmail_sync_job",
                status="FAILED",
                error_message=str(e)
            )
        except Exception:
            pass

async def scheduler_loop():
    """Infinite loop sleeping for 5 minutes (300s) between runs."""
    global _running
    _running = True
    await asyncio.sleep(10)
    
    while _running:
        try:
            await run_sync_cycle()
        except Exception as e:
            logger.error(f"Error in scheduler loop execution: {e}")
        await asyncio.sleep(300)

def start_scheduler(app):
    """Register startup and shutdown events to uvicorn/fastapi."""
    global _scheduler_task
    
    @app.on_event("startup")
    async def startup_event():
        global _scheduler_task
        logger.info("Starting background scheduler loop...")
        _scheduler_task = asyncio.create_task(scheduler_loop())

    @app.on_event("shutdown")
    async def shutdown_event():
        global _running
        logger.info("Stopping background scheduler loop...")
        _running = False
        if _scheduler_task:
            _scheduler_task.cancel()
            try:
                await _scheduler_task
            except asyncio.CancelledError:
                pass
            logger.info("Background scheduler loop stopped.")
