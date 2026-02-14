import logging
import azure.functions as func

app = func.FunctionApp()

@app.timer_trigger(schedule="0 0 * * * *", arg_name="myTimer", run_on_startup=False)
def reddit_podcast_timer(myTimer: func.TimerRequest) -> None:
    """
    CRON TRIGGER: Runs every hour on the hour.
    Orchestrates the full Reddit-to-Podcast pipeline automatically.
    """
    import main 
    
    logging.info("🚀 Starting Reddit-to-Podcast Pipeline...")
    try:
        main.run_pipeline()
    except Exception as e:
        logging.error(f"❌ Pipeline failed: {str(e)}")

@app.route(route="manual_run", auth_level=func.AuthLevel.FUNCTION)
def manual_run(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP TRIGGER: Allows manual execution via a secret URL.
    Useful for testing or forcing a run outside the hourly schedule.
    """
    import main
    main.run_pipeline()
    return func.HttpResponse("Pipeline triggered.", status_code=200)
