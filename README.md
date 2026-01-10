# SlotlyMed Backend - Google Sheets Integration

Backend serverless com integração Google Sheets para o sistema SlotlyMed.

## 📋 Estrutura de Arquivos

```
slotlymed-backend/
├── api/
│   ├── schedule.py           (JÁ EXISTE - Geração de slots com IA)
│   ├── get_doctor.py         (NOVO - Buscar dados do médico)
│   ├── save_doctor.py        (NOVO - Salvar configuração médico)
│   ├── get_slots.py          (NOVO - Buscar slots disponíveis)
│   └── book_appointment.py   (NOVO - Criar agendamento)
├── sheets_client.py          (NOVO - Cliente Google Sheets)
├── requirements.txt          (ATUALIZADO - Dependências)
└── README.md
```

## 🔧 Configuração no Vercel

### 1. Variáveis de Ambiente

Adicione estas variáveis no painel do Vercel (Settings → Environment Variables):

#### `OPENAI_API_KEY`
- Valor: Sua chave da OpenAI
- Status: ✅ JÁ CONFIGURADA

#### `GOOGLE_CREDENTIALS_JSON`
- Valor: Cole TODO o conteúdo do arquivo JSON da service account
- Formato: JSON em uma linha (remova quebras de linha)
- Exemplo:
```json
{"type":"service_account","project_id":"slotlymed",...}
```

#### `SPREADSHEET_ID`
- Valor: ID da sua planilha Google Sheets
- Como obter: Pegue da URL da planilha
- URL: `https://docs.google.com/spreadsheets/d/1jXztoDuQBDeZ_zSE_3_BJYaunyRtYn6u37bR7pALWG0/edit`
- ID: `1jXztoDuQBDeZ_zSE_3_BJYaunyRtYn6u37bR7pALWG0`

### 2. Deploy

```bash
# Commit e push para GitHub
git add .
git commit -m "Add Google Sheets integration"
git push origin main
```

Vercel fará deploy automático!

## 📡 Endpoints Disponíveis

### 1. GET /api/get_doctor
Busca dados de um médico pelo ID

**Query Parameters:**
- `id` (required): ID único do médico (ex: "dr-joao")

**Response:**
```json
{
  "success": true,
  "doctor": {
    "id": "dr-joao",
    "name": "Dr. João Silva",
    "specialty": "Cardiologista",
    "address": "Av. Paulista, 1000",
    "phone": "+55 11 98765-4321",
    "email": "drjoao@example.com",
    "logo_url": "https://...",
    "color": "#3B82F6",
    "language": "pt",
    "welcome_message": "Bem-vindo!",
    "link": "dr-joao"
  }
}
```

### 2. POST /api/save_doctor
Salva configuração do médico e slots

**Body (JSON):**
```json
{
  "id": "dr-joao",
  "name": "Dr. João Silva",
  "specialty": "Cardiologista",
  "address": "Av. Paulista, 1000",
  "phone": "+55 11 98765-4321",
  "email": "drjoao@example.com",
  "logo_url": "https://...",
  "color": "#3B82F6",
  "language": "pt",
  "welcome_message": "Bem-vindo!",
  "link": "dr-joao",
  "slots": [
    {"date": "2026-01-10", "time": "09:00", "status": "available"},
    {"date": "2026-01-10", "time": "09:30", "status": "available"}
  ]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Doctor configuration saved successfully",
  "doctor_id": "dr-joao",
  "link": "https://slotlymed.com/dr-joao",
  "slots_saved": 720
}
```

### 3. GET /api/get_slots
Busca slots disponíveis

**Query Parameters:**
- `doctor_id` (required): ID do médico
- `date` (optional): Filtrar por data específica (YYYY-MM-DD)

**Response:**
```json
{
  "success": true,
  "doctor_id": "dr-joao",
  "date": "2026-01-10",
  "slots": [
    {"date": "2026-01-10", "time": "09:00", "status": "available"},
    {"date": "2026-01-10", "time": "09:30", "status": "available"}
  ],
  "count": 2
}
```

### 4. POST /api/book_appointment
Cria novo agendamento

**Body (JSON):**
```json
{
  "doctor_id": "dr-joao",
  "patient_name": "Maria Silva",
  "patient_email": "maria@example.com",
  "patient_phone": "+55 11 91234-5678",
  "date": "2026-01-10",
  "time": "09:00",
  "notes": "Primeira consulta"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Appointment booked successfully",
  "appointment_id": 1,
  "appointment": {
    "date": "2026-01-10",
    "time": "09:00",
    "patient_name": "Maria Silva"
  }
}
```

### 5. POST /api/schedule (JÁ EXISTENTE)
Gera slots com IA - mantém funcionamento atual

## 🗄️ Estrutura Google Sheets

### Aba: doctors
| id | name | specialty | address | phone | email | logo_url | color | language | welcome_message | link |

### Aba: availability
| doctor_id | date | time | status |

### Aba: appointments
| id | doctor_id | patient_name | patient_email | patient_phone | date | time | notes | created_at |

## ✅ Checklist de Deploy

- [ ] Arquivo JSON da service account baixado
- [ ] Planilha Google Sheets criada com 3 abas
- [ ] Service account adicionada como Editor na planilha
- [ ] Variável `GOOGLE_CREDENTIALS_JSON` configurada no Vercel
- [ ] Variável `SPREADSHEET_ID` configurada no Vercel
- [ ] Código commitado e pushed para GitHub
- [ ] Deploy no Vercel concluído
- [ ] Testar endpoint `/api/get_doctor?id=test`
- [ ] Testar endpoint `/api/save_doctor` com POST

## 🧪 Como Testar

### Teste 1: Salvar Médico
```bash
curl -X POST https://slotlymed-backend.vercel.app/api/save_doctor \
  -H "Content-Type: application/json" \
  -d '{
    "id": "dr-test",
    "name": "Dr. Test",
    "address": "Test St",
    "phone": "+1234567890",
    "email": "test@test.com",
    "language": "en",
    "link": "dr-test"
  }'
```

### Teste 2: Buscar Médico
```bash
curl https://slotlymed-backend.vercel.app/api/get_doctor?id=dr-test
```

## 🔒 Segurança

- ✅ API keys em variáveis de ambiente
- ✅ CORS configurado
- ✅ Validação de inputs
- ✅ Credenciais Google nunca expostas no código
- ✅ Verificação de link único antes de salvar

## 📊 Custos

- Google Sheets API: **Grátis** (até 500 requests/min)
- Vercel Serverless: **Grátis** (até 100GB bandwidth)
- Total: **$0/mês** para começar

## 🆘 Troubleshooting

### Erro: "GOOGLE_CREDENTIALS_JSON not set"
- Verifique se a variável está configurada no Vercel
- Confirme que é um JSON válido (sem quebras de linha)

### Erro: "Permission denied"
- Verifique se a service account foi adicionada como Editor na planilha
- Confirme o email: `slotlymed-bot@slotlymed.iam.gserviceaccount.com`

### Erro: "Spreadsheet not found"
- Verifique o SPREADSHEET_ID na variável de ambiente
- Confirme que a planilha existe e está acessível

## 📝 Próximos Passos

1. ✅ Testar todas as APIs
2. ⏳ Integrar frontend com backend
3. ⏳ Adicionar sistema de emails
4. ⏳ Implementar landing page
5. ⏳ Configurar pagamento (Stripe/Gumroad)
