import os
import csv
import json
import time
import logging
import smtplib
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Set
from dataclasses import dataclass
from abc import ABC, abstractmethod
import re
from dotenv import load_dotenv
import sys
from enum import Enum

load_dotenv()

class ActivityType(Enum):
    PALESTRA = "palestra"
    TUTORIAL = "tutorial"


@dataclass
class Speaker:
    name: str
    email: str
    title: str
    theme: str
    all_authors: str
    activity_type: ActivityType

    @property
    def is_tutorial(self) -> bool:
        return self.activity_type == ActivityType.TUTORIAL

    @property
    def activity_display_name(self) -> str:
        return self.activity_type.value


@dataclass
class EmailConfig:
    smtp_server: str
    smtp_port: int
    sender_email: str
    sender_password: str
    sender_name: str
    sheet_url: str

    @classmethod
    def from_env(cls) -> 'EmailConfig':
        return cls(
            smtp_server=os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
            smtp_port=int(os.getenv('SMTP_PORT', 587)),
            sender_email=os.getenv('GMAIL_EMAIL', ''),
            sender_password=os.getenv('GMAIL_APP_PASSWORD', ''),
            sender_name=os.getenv('SENDER_NAME', 'Equipe Organizadora Python Norte 2025'),
            sheet_url=os.getenv('SHEET_URL', '')
        )

    def validate(self) -> List[str]:
        errors = []
        if not self.sender_email:
            errors.append("Email do remetente (GMAIL_EMAIL) não configurado")
        if not self.sender_password:
            errors.append("Senha do remetente (GMAIL_APP_PASSWORD) não configurada")
        if not self.sheet_url:
            errors.append("URL da planilha (SHEET_URL) não configurada")
        return errors


class LoggerSetup:
    @staticmethod
    def configure(log_file: str = 'logs/campaign.log') -> logging.Logger:
        # Garante que o diretório de logs exista
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)s | %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(stream=sys.stdout)
            ]
        )

        logger = logging.getLogger(__name__)

        if os.name == 'nt' and sys.stdout.isatty():
            try:
                sys.stdout.reconfigure(encoding='utf-8')
                sys.stderr.reconfigure(encoding='utf-8')
            except Exception:
                pass

        return logger


class DataStore(ABC):
    @abstractmethod
    def load(self) -> Set[str]:
        pass

    @abstractmethod
    def save(self, speaker: Speaker) -> None:
        pass


class JsonDataStore(DataStore):
    def __init__(self, file_path: str):
        # Garante que o diretório exista
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        self.file_path = file_path
        self._data = self._load_data()

    def _load_data(self) -> dict:
        if not os.path.exists(self.file_path):
            return {'sent_titles': [], 'details': []}

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            return {'sent_titles': [], 'details': []}

    def load(self) -> Set[str]:
        sent_titles = set(self._data.get('sent_titles', []))

        if not sent_titles and 'details' in self._data:
            for detail in self._data['details']:
                if isinstance(detail, dict) and 'titulo' in detail:
                    sent_titles.add(detail['titulo'])

        return sent_titles

    def save(self, speaker: Speaker) -> None:
        sent_titles = self.load()
        sent_titles.add(speaker.title)

        self._data['sent_titles'] = list(sent_titles)
        self._data['last_update'] = datetime.now().isoformat()

        if 'details' not in self._data:
            self._data['details'] = []

        self._data['details'].append({
            'email': speaker.email,
            'nome': speaker.name,
            'titulo': speaker.title,
            'timestamp': datetime.now().isoformat()
        })

        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, indent=4, ensure_ascii=False)


class SpreadsheetDownloader:
    @staticmethod
    def extract_sheet_id(url: str) -> str:
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
        if not match:
            raise ValueError("URL do Google Sheets inválida")
        return match.group(1)

    @staticmethod
    def download(sheet_url: str) -> str:
        sheet_id = SpreadsheetDownloader.extract_sheet_id(sheet_url)
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

        response = requests.get(csv_url)
        response.raise_for_status()

        # Diretório para armazenar arquivos CSV
        dir_name = "speakers"
        os.makedirs(dir_name, exist_ok=True)

        filename = f"speakers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path = os.path.join(dir_name, filename)
        with open(file_path, 'wb') as f:
            f.write(response.content)

        return file_path


class CsvParser:
    REQUIRED_FIELDS = ['ATIVIDADE', 'AUTOR1', 'EMAIL', 'TEMA']

    @staticmethod
    def parse(csv_file: str) -> List[Speaker]:
        speakers = []

        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                parsed_speakers = CsvParser._parse_row(row)
                speakers.extend(parsed_speakers)

        return speakers

    @staticmethod
    def _parse_row(row: Dict[str, str]) -> List[Speaker]:
        activity = row.get('ATIVIDADE', '').strip()
        theme = row.get('TEMA', '').strip()
        email = row.get('EMAIL', '').strip()

        authors = CsvParser._extract_authors(row)

        if not all([activity, theme, email, authors]):
            return []

        activity_type = CsvParser._get_activity_type(activity)
        emails = CsvParser._parse_emails(email)

        speakers = []
        for i, individual_email in enumerate(emails):
            if '@' in individual_email:
                author_name = authors[i] if i < len(authors) else authors[0]
                speakers.append(Speaker(
                    name=author_name,
                    email=individual_email,
                    title=theme,
                    theme=theme,
                    all_authors=', '.join(authors) if len(authors) > 1 else authors[0],
                    activity_type=activity_type
                ))

        return speakers

    @staticmethod
    def _extract_authors(row: Dict[str, str]) -> List[str]:
        authors = []
        for i in range(1, 4):
            author = row.get(f'AUTOR{i}', '').strip()
            if author:
                authors.append(author)
        return authors

    @staticmethod
    def _get_activity_type(activity: str) -> ActivityType:
        if activity.lower() == 'tutorial':
            return ActivityType.TUTORIAL
        return ActivityType.PALESTRA

    @staticmethod
    def _parse_emails(email: str) -> List[str]:
        if ',' in email:
            return [e.strip() for e in email.split(',')]
        return [email]


class EmailTemplate:
    TEMPLATE = """Prezad@ {name},

    É com grande satisfação que informamos que {article} {activity}, "{title}", foi aprovad{approval_suffix} para a conferência! 🚀

O evento acontecerá nos dias 04, 05 e 06 de julho de 2025, em Belém do Pará, e contará com a participação de entusiastas, desenvolvedores e especialistas em Python de todo o país. Sua contribuição será fundamental para enriquecer nossa programação!

Próximos passos:

Para confirmar sua participação como {role}, pedimos que nos envie sua confirmação até o dia 10/06/2025 respondendo a este e-mail.

Caso não recebamos sua confirmação até essa data, entenderemos que não há disponibilidade e sua vaga poderá ser realocada.

Informações importantes:

📅 Datas do evento: 04, 05 e 06 de julho de 2025
📍 Local: Belém - PA
⏰ {duration_label}: 45 minutos
🎯 Tema: {theme}
{coauthors_info}

Ficamos à disposição para qualquer dúvida e ansiosos pela sua confirmação!

Atenciosamente,
    Equipe Organizadora
    Contato: contato@evento.org | Site: https://evento.org"""

    @staticmethod
    def render(speaker: Speaker) -> str:
        context = EmailTemplate._build_context(speaker)
        return EmailTemplate.TEMPLATE.format(**context)

    @staticmethod
    def _build_context(speaker: Speaker) -> dict:
        is_tutorial = speaker.is_tutorial

        coauthors_info = ""
        if ',' in speaker.all_authors:
            coauthors_info = f"\n👥 Coautores: {speaker.all_authors}"

        return {
            'name': speaker.name,
            'title': speaker.title,
            'theme': speaker.theme,
            'activity': speaker.activity_display_name,
            'article': 'seu' if is_tutorial else 'sua',
            'approval_suffix': 'o' if is_tutorial else 'a',
            'role': 'instrutor(a) de tutorial' if is_tutorial else 'palestrante',
            'duration_label': 'Duração do tutorial' if is_tutorial else 'Duração da palestra',
            'coauthors_info': coauthors_info
        }


class EmailService:
    def __init__(self, config: EmailConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def send(self, speaker: Speaker, body: str) -> bool:
        msg = self._create_message(speaker, body)

        try:
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.sender_email, self.config.sender_password)
                server.send_message(msg)
            return True
        except Exception as e:
            self.logger.error(f"Falha ao enviar e-mail para {speaker.email}: {e}")
            return False

    def _create_message(self, speaker: Speaker, body: str) -> MIMEMultipart:
        msg = MIMEMultipart()
        msg['From'] = f"{self.config.sender_name} <{self.config.sender_email}>"
        msg['To'] = speaker.email
        msg['Subject'] = speaker.title
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        return msg


class CampaignStats:
    def __init__(self, total: int, sent: int, pending: int):
        self.total = total
        self.sent = sent
        self.pending = pending

    def display(self, logger: logging.Logger) -> None:
        logger.info(f"📊 Total de palestrantes identificados: {self.total}")
        logger.info(f"📧 Novas comunicações a serem enviadas: {self.pending}")
        logger.info(f"✅ Temas já processados: {self.sent}")


class EmailCampaignManager:
    def __init__(
            self,
            config: EmailConfig,
            data_store: DataStore,
            logger: logging.Logger
    ):
        self.config = config
        self.data_store = data_store
        self.logger = logger
        self.email_service = EmailService(config, logger)
        self.sent_titles = data_store.load()

    def run(self, dry_run: bool = False) -> None:
        self.logger.info("🐍 Iniciando campanha de e-mails - Python Norte 2025")

        validation_errors = self.config.validate()
        if validation_errors:
            for error in validation_errors:
                self.logger.error(f"❌ {error}")
            return

        try:
            csv_file = SpreadsheetDownloader.download(self.config.sheet_url)
            speakers = CsvParser.parse(csv_file)

            new_speakers = self._filter_new_speakers(speakers)
            stats = self._calculate_stats(speakers, new_speakers)
            stats.display(self.logger)

            if not new_speakers:
                self.logger.info("Nenhuma nova comunicação para enviar!")
                return

            if not dry_run and not self._confirm_send(len(new_speakers)):
                return

            self._process_speakers(new_speakers, dry_run)

        except Exception as e:
            self.logger.error(f"Erro na campanha: {e}")
            raise

    def _filter_new_speakers(self, speakers: List[Speaker]) -> List[Speaker]:
        return [s for s in speakers if s.title not in self.sent_titles]

    def _calculate_stats(
            self,
            all_speakers: List[Speaker],
            new_speakers: List[Speaker]
    ) -> CampaignStats:
        return CampaignStats(
            total=len(all_speakers),
            sent=len(self.sent_titles),
            pending=len(new_speakers)
        )

    def _confirm_send(self, count: int) -> bool:
        print(f"\n⚠️  ATENÇÃO: {count} e-mails serão enviados!")
        response = input("Continuar? (s/N): ").strip().lower()
        return response == 's'

    def _process_speakers(self, speakers: List[Speaker], dry_run: bool) -> None:
        success = 0
        failures = 0

        for i, speaker in enumerate(speakers, 1):
            self.logger.info(f"\n[{i}/{len(speakers)}] Processando {speaker.name}...")

            if self._send_to_speaker(speaker, dry_run):
                success += 1
            else:
                failures += 1

            if not dry_run and i < len(speakers):
                time.sleep(2)

        self._display_summary(success, failures)

    def _send_to_speaker(self, speaker: Speaker, dry_run: bool) -> bool:
        if speaker.title in self.sent_titles:
            self.logger.info(f"Tema '{speaker.title}' já enviado")
            return True

        body = EmailTemplate.render(speaker)

        if dry_run:
            self.logger.info(
                f"[MODO TESTE] Enviaria '{speaker.title}' para: "
                f"{speaker.name} <{speaker.email}>"
            )
            return True

        if self.email_service.send(speaker, body):
            self.logger.info(
                f"✅ Enviado '{speaker.title}' para: "
                f"{speaker.name} <{speaker.email}>"
            )
            self.data_store.save(speaker)
            self.sent_titles.add(speaker.title)
            return True

        return False

    def _display_summary(self, success: int, failures: int) -> None:
        self.logger.info("\n" + "=" * 50)
        self.logger.info("📊 RESUMO:")
        self.logger.info(f"✅ Enviados com sucesso: {success}")
        self.logger.info(f"❌ Falhas: {failures}")


class Application:
    def __init__(self):
        self.logger = LoggerSetup.configure()
        self.config = EmailConfig.from_env()
        self.data_store = JsonDataStore('data/campaign_history.json')
        self.manager = EmailCampaignManager(
            self.config,
            self.data_store,
            self.logger
        )

    def run(self) -> None:
        self._display_header()
        choice = self._get_user_choice()

        actions = {
            '1': lambda: self.manager.run(dry_run=False),
            '2': lambda: self._run_test_mode(),
            '3': lambda: self._display_statistics()
        }

        action = actions.get(choice)
        if action:
            action()
        else:
            print("Opção inválida!")

    def _display_header(self) -> None:
        print("🐍 Sistema de Campanha de E-mails - Python Norte 2025")
        print("=" * 50)
        print("\nOpções:")
        print("1. Enviar e-mails (produção)")
        print("2. Modo de teste (simulação)")
        print("3. Ver estatísticas")

    def _get_user_choice(self) -> str:
        return input("\nEscolha uma opção (1-3): ").strip()

    def _run_test_mode(self) -> None:
        print("\n🔍 MODO TESTE - Nenhum e-mail será enviado")
        self.manager.run(dry_run=True)

    def _display_statistics(self) -> None:
        sent_titles = self.data_store.load()
        print(f"\n📊 Estatísticas:")
        print(f"Total de temas processados: {len(sent_titles)}")

        if sent_titles:
            print("\nTemas processados:")
            for title in sorted(sent_titles):
                print(f"  - {title}")


def main():
    app = Application()
    app.run()


if __name__ == "__main__":
    main()