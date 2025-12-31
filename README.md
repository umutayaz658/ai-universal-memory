# 🏜️ Nomad MemorAI

> **Your External Brain for the AI Era.** > Unbound context, universal memory, and smart logic for ChatGPT, Gemini, DeepSeek, Mistral & Perplexity.

<p align="center">
  <img src="logo.png" alt="Nomad MemorAI Logo" width="128"/>
</p>

## 🚀 Overview

**Nomad MemorAI** is a powerful Chrome Extension and Django Backend ecosystem designed to liberate your data from closed AI silos. Instead of repeating your project details, rules, and preferences to every new chat session, Nomad MemorAI injects the relevant context automatically.

It uses **Vector Embeddings (pgvector)** to understand semantic meaning, allowing it to fetch the exact memory you need, right when you need it.

### ✨ Key Features

* **Universal Injection:** Works seamlessly on ChatGPT, Gemini, DeepSeek, Mistral, and Perplexity.
* **🧠 Context-Aware Logic:** Unlike simple storage, Nomad acts as an intelligent layer.
    * **Smart Math:** Knows that "Adding 50k to budget" means `Old Budget + 50k`.
    * **Date Resolution:** Converts relative dates ("next week") into exact ISO dates (`2026-01-07`) for AI precision.
* **Vector Search:** Uses Cosine Similarity to find relevant memories even if keywords don't match exactly.
* **Project Management:** Organize memories into distinct workspaces (e.g., "Client X", "Novel Draft", "Coding Project").
* **Privacy-First UI:** Clean, "Nomad Daylight" aesthetic designed for focus.
* **Export Data:** Generate Markdown or PDF reports of your project memory instantly.

---

## 🛠️ Tech Stack

* **Frontend:** Chrome Extension (Manifest V3), JavaScript, HTML5, CSS3 (Modern Variables).
* **Backend:** Python, Django REST Framework.
* **Database:** PostgreSQL with **`pgvector`** extension.
* **AI Engine:** Google Gemini API (Flash-Lite & Text-Embedding-004).
* **Containerization:** Docker & Docker Compose.

---

## ⚙️ Installation & Setup

### 1. Backend Setup (Docker)

Prerequisites: Docker Desktop installed.

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/YOUR_USERNAME/Nomad-MemorAI.git](https://github.com/YOUR_USERNAME/Nomad-MemorAI.git)
    cd Nomad-MemorAI
    ```

2.  **Environment Variables:**
    Create a `.env` file in the root directory and add your keys:
    ```env
    GOOGLE_API_KEY=your_gemini_api_key_here
    DJANGO_SECRET_KEY=your_secure_django_key
    DEBUG=True
    ```

3.  **Build and Run:**
    ```bash
    docker-compose up --build
    ```
    *The server will start at `http://localhost:8000`.*

4.  **Initialize Database (First Time Only):**
    Enable the vector extension and migrate:
    ```bash
    # Open a new terminal
    docker-compose exec web python manage.py makemigrations core --empty --name enable_vector_extension
    # Edit the migration file to add VectorExtension() (See docs if needed)
    docker-compose exec web python manage.py migrate
    ```

### 2. Extension Setup (Chrome)

1.  Open Chrome and navigate to `chrome://extensions`.
2.  Enable **Developer Mode** (top right toggle).
3.  Click **Load unpacked**.
4.  Select the root folder of this project.
5.  📌 **Pin the Nomad MemorAI icon** to your toolbar for easy access.

---

## 📖 How to Use

### 1. Create a Workspace
Open the extension, go to the "New Project" section, and give your workspace a name (e.g., "Project Alpha").

### 2. Teach the AI
You don't need to manually type everything into the database. Just use your AI chatbot!
* **Open ChatGPT/Gemini:** Start talking about your project.
* **Nomad Listens:** When you confirm details, Nomad analyzes the conversation using `ai_services` and saves facts automatically.
* **Manual Entry:** You can also type directly into the chat: *"Nomad, remember that the deadline is 2026-05-01."*

### 3. Inject Context
When you start a new chat:
* **Press Enter Once:** Nomad fetches relevant history and injects it invisibly into the prompt context.
* **Press Enter Again:** The message is sent to the AI with full context awareness.

### 4. Commands
* `/delete keyword`: Deletes memories matching the keyword.
* `Export Data`: Download a full report of your project from the extension footer.

---

## 📸 Screenshots

| Login Screen | Main Workspace |
|:---:|:---:|
| <img src="docs/login.png" width="300"> | <img src="docs/dashboard.png" width="300"> |

*(Note: Add your screenshots to a `docs/` folder to display them here)*

---

## 🤝 Contributing

Contributions are welcome! Please fork the repository and submit a pull request for any features or bug fixes.

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

---

## 📄 License

**PROPRIETARY / PERSONAL USE LICENSE**

Copyright (c) 2025 **Umut Ayazoğlu**

This software is protected by copyright law. By using this software, you agree to the following terms:

1.  **Grant of License:** This software is provided for **personal study, evaluation, and non-commercial use only**.
2.  **Restrictions:**
    * Commercial use of this software or its source code is **STRICTLY PROHIBITED**.
    * Redistribution of this code for commercial purposes is not allowed.
    * You may not sell, rent, or lease this software.
3.  **No Warranty:** The software is provided "as is" without warranty of any kind.

For commercial licensing inquiries, please contact the author.