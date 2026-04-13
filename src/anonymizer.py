from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

class AnonymizerTool:
    def __init__(self, entities, threshold):
        # Alustetaan Presidion moottorit
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self.entities = entities
        self.threshold = threshold

    def process_text(self, text):
        # 1. Analysoidaan teksti ja etsitään arkaluonteiset tiedot
        results = self.analyzer.analyze(
            text=text, 
            entities=self.entities, 
            language='en', 
            score_threshold=self.threshold
        )
        
        # 2. Anonymisoidaan löydökset (korvataan ne tunnisteilla kuten [PERSON])
        anonymized_result = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results
        )
        
        return anonymized_result.text, results