import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel
from sklearn.metrics.pairwise import cosine_similarity
import gensim
from gensim.models.doc2vec import Doc2Vec, TaggedDocument
import nltk
from nltk.tokenize import word_tokenize

# Mean Pooling - Take attention mask into account for correct averaging
def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output[0]  # First element contains all token embeddings
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

# Get HuggingFace BERT embeddings
def get_HF_embeddings(sentences):
    tokenizer = AutoTokenizer.from_pretrained('sentence-transformers/bert-base-nli-mean-tokens')
    model = AutoModel.from_pretrained('sentence-transformers/bert-base-nli-mean-tokens')
    
    encoded_input = tokenizer(sentences, padding=True, truncation=True, return_tensors='pt', max_length=512)
    
    with torch.no_grad():
        model_output = model(**encoded_input)
    
    embeddings = mean_pooling(model_output, encoded_input['attention_mask'])
    return embeddings

# Compare resumes to JD
def compare(resume_texts, JD_text, flag='HuggingFace-BERT'):
    JD_embeddings = None
    resume_embeddings = []

    if flag == 'HuggingFace-BERT':
        if JD_text is not None:
            JD_embeddings = get_HF_embeddings(JD_text)
        for resume_text in resume_texts:
            resume_embeddings.append(get_HF_embeddings(resume_text))

        # Check if JD_embeddings and each element in resume_embeddings are valid
        if JD_embeddings is not None and all(embedding.numel() > 0 for embedding in resume_embeddings):
            cos_scores = cosine(resume_embeddings, JD_embeddings)
            return cos_scores
    # Add logic for other flags like 'Doc2Vec' if necessary
    else:
        # Handle other cases
        pass


# Cosine similarity calculation
def cosine(embeddings1, embeddings2):
    score_list = []
    for i in embeddings1:
        match_percentage = cosine_similarity(np.array(i), np.array(embeddings2))
        match_percentage = np.round(match_percentage, 4) * 100
        score_list.append(str(match_percentage[0][0]))
    return score_list

# Doc2Vec embeddings (if needed for other methods)
def get_doc2vec_embeddings(JD, text_resume):
    nltk.download("punkt")
    data = [JD]
    resume_embeddings = []
    
    tagged_data = [TaggedDocument(words=word_tokenize(_d.lower()), tags=[str(i)]) for i, _d in enumerate(data)]
    
    model = gensim.models.doc2vec.Doc2Vec(vector_size=512, min_count=3, epochs=80)
    model.build_vocab(tagged_data)
    model.train(tagged_data, total_examples=model.corpus_count, epochs=80)
    JD_embeddings = np.transpose(model.docvecs['0'].reshape(-1, 1))

    for i in text_resume:
        text = word_tokenize(i.lower())
        embeddings = model.infer_vector(text)
        resume_embeddings.append(np.transpose(embeddings.reshape(-1, 1)))
    return JD_embeddings, resume_embeddings