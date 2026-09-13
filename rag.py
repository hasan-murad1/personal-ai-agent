import os
import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader
import docx

CHROMA_PATH = "chroma_db"
COLLECTION_NAME = "personal_documents"

embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    embedding_function=embedding_function
)


def extract_text(file_path):
    if file_path.endswith(".pdf"):
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif file_path.endswith(".docx"):
        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        return None


def chunk_text(text, chunk_size=100, overlap=20):
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def ingest_document(file_path):
    text = extract_text(file_path)
    if not text:
        return f"Could not extract text from {file_path}"

    chunks = chunk_text(text)
    file_name = os.path.basename(file_path)

    ids = [f"{file_name}_{i}" for i in range(len(chunks))]
    metadatas = [{"source": file_name} for _ in chunks]

    collection.add(
        documents=chunks,
        ids=ids,
        metadatas=metadatas
    )

    return f"Ingested {len(chunks)} chunks from {file_name}"


def ingest_folder(folder_path="documents"):
    results = []
    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)
        if file_name.endswith((".pdf", ".docx")):
            result = ingest_document(file_path)
            results.append(result)
    return results


def search_documents(query: str, n_results: int = 3) -> str:
    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )

    if not results["documents"][0]:
        return "No relevant documents found."

    output = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        output.append(f"[Source: {meta['source']}]\n{doc}")

    return "\n\n".join(output)