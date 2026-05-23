import logging
import json
from server import run_pipeline

# Configurazione del logger per scrivere sia su file che su console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("server_test.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

class ServerTester:
    """Classe per testare le funzioni di server.py e tracciarne i log."""
    
    def __init__(self):
        self.logger = logging.getLogger("ServerTester")

    def test_run_pipeline(self, question: str, document_name: str = "OpenAI-Privacy-Filter-Model-Card.pdf"):
        self.logger.info("=" * 60)
        self.logger.info(" AVVIO TEST PIPELINE LOCALE")
        self.logger.info("=" * 60)
        self.logger.info(f"Domanda in elaborazione: '{question}'")
        self.logger.info(f"Documento target: '{document_name}'")
        
        try:
            # Eseguiamo la pipeline importata bypassando il server FastMCP
            result = run_pipeline(
                question=question,
                document_name=document_name,
                top_k=2,
                threshold=0.7,
                model="gpt-4o-mini"
            )
            
            self.logger.info("\nRISULTATO DELLA PIPELINE:")
            self.logger.info(json.dumps(result, indent=2, ensure_ascii=False))
            return result
        except Exception as e:
            self.logger.error(f"Errore fatale durante il test: {e}", exc_info=True)

if __name__ == "__main__":
    tester = ServerTester()
    tester.test_run_pipeline("What are the main risks and limitations of the Privacy Filter model?")
