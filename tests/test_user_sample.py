import unittest

from src.modalities.audio.audio_pipeline import _normalize_spoken_email_markers
from src.anonymizer import AnonymizerTool


class UserSampleRegression(unittest.TestCase):
    def test_user_voice_sample_anonymized(self):
        voice_text = (
            "Uusi työntekijä Sami Korpela aloitti työskentelyn Turun tehtaalla maanantaina. "
            "Hänen esimiehenään toimii Katja Mäkinen tehtaan Linjaosastolla. "
            "Koulutuksessa käytiin läpi turvallisuusvaiheita ja laitteiden käyttöä. "
            "Työntekijä pitää käyttää silmiensuojaimia ja teflonkäsineitä kaikissa pääty työasemissa. "
            "Työtehtävät sisältävät komponenttien tarkistusta ja laadunvalvontaa. "
            "Kahvitauko on kello 10:30 ja ruokailu kello 12:00 toimistolla. "
            "Päivittäinen työaika on kahdeksasta neljään. "
            "Jos kysyttävää, voi ottaa yhteyttä pomo Tero Rajalle numeroilla 040-555-1234 "
            "tai sähköpostilla tero . raja . company . fi."
        )

        # Simulate the audio normalization step first
        normalized = _normalize_spoken_email_markers(voice_text)

        tool = AnonymizerTool(
            entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION"],
            threshold=0.3,
            policy_name="light",
        )

        anonymized, results = tool.process_text(normalized)

        # Names should be anonymized
        self.assertIn("[NAME", anonymized)
        # Phone should be anonymized
        self.assertIn("[PHONE", anonymized)
        # Email should be anonymized (after normalization)
        self.assertIn("[EMAIL", anonymized)


if __name__ == "__main__":
    unittest.main()
