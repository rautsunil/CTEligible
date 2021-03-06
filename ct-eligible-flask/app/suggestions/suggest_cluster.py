from app import mongo
from app.suggestions.suggestions_utils import \
    clean_text, get_cluster_text, convert_to_frequency
from app.suggestions.tfidf_converter import TfidfConverter
import operator
import math
from BeautifulSoup import BeautifulSoup


def get_text_from_mongo():
    cluster_text = dict()
    cursor = mongo.db.clusters.find({})
    for clust in cursor:
        cluster_text[clust['_id']] = clust['suggestions']
    return cluster_text


def get_ctep_from_mongo():
    ctep = {}
    cursor = mongo.db.ctep.find({})
    for ctep in cursor:
        ctep[ctep['_id']] = ctep['suggestions']
    return ctep


def get_text_from_dir(path):
    return get_cluster_text(path)


def dot_product(d1, d2):
    dot = 0.0
    for term in d1.keys():
        val1 = d1[term]
        val2 = d2.get(term, 0.0)

        dot += val1 * val2

    return dot


class ClusterSuggestor:
    def __init__(self, from_mongo=True):
        self.cluster_text = {}
        if from_mongo:
            self.cluster_text = get_text_from_mongo()
        else:
            self.cluster_text = get_text_from_dir(
                '/home/jaojao/hackathon/clusters/')

        self.ctep = get_ctep_from_mongo()
        self.idf = {}
        self.cluster_tfidf = {}

    def suggest(self, input_text, n=1):
        soup = BeautifulSoup(input_text)
        bullets = soup.findAll('li')
        ptags = soup.findAll('p')

        criteria = []
        if bullets:
            for bullet in bullets:
                criteria.append(bullet.getText())

        elif ptags:
            for ptag in ptags:
                criteria.append(ptag.getText())

        else:
            criteria.append(input_text)

        suggestions = []
        for criterion in criteria:
            suggestion = self.suggest_for_one(criterion)
            suggestions.append(suggestion)

        return suggestions

    def suggest_for_one(self, input_text, n=1):
        if not self.cluster_tfidf:
            self.get_cluster_tfidf_vectors()

        input_tfidf = self.convert_to_tfidf(input_text)

        output = {
            "text": input_text,
            "data_suggestion": [],
            "ctep_suggestion": []
        }
        if input_tfidf:
            similarity = []  # (cluster, sim_score to input)
            for cluster, cluster_tfidf in self.cluster_tfidf.items():
                similarity.append(
                    (cluster, self.cosine(cluster_tfidf, input_tfidf)))

            sorted_clusters_by_sim = sorted(
                similarity, key=operator.itemgetter(1), reverse=True)

            closest_cluster = sorted_clusters_by_sim[0][0]

            possible_suggestions = self.cluster_text[closest_cluster]
            suggestions = possible_suggestions[:n]

            output["text"] = input_text
            output["data_suggestion"] = suggestions

            ctep = self.get_ctep_suggestions(input_tfidf)

            if ctep:
                output["ctep_suggestion"] = ctep

        return output

    def get_ctep_suggestions(self, input_tfidf, n=1):
        most_relevant_term = max(
            input_tfidf.items(), key=operator.itemgetter(1))[0]

        possible_ctep_suggestions = []
        for ctep_id, suggestions in self.ctep.items():
            for suggestion in suggestions:
                cleaned = clean_text(suggestion)

                if most_relevant_term in cleaned:
                    possible_ctep_suggestions.append(suggestion)

        return possible_ctep_suggestions[:n]

    def cosine(self, cluster_tfidf, input_tfidf):
        dot = dot_product(cluster_tfidf, input_tfidf)
        cluster_2_norm = math.sqrt(dot_product(cluster_tfidf, cluster_tfidf))
        input_2_norm = math.sqrt(dot_product(input_tfidf, input_tfidf))

        return dot / (cluster_2_norm * input_2_norm)

    def convert_to_tfidf(self, input_text):
        tokens = clean_text(input_text)
        freq_vector = convert_to_frequency(tokens)
        total = float(sum(freq for freq in freq_vector.values()))

        input_tfidf = {}
        for term, count in freq_vector.items():
            if term not in self.idf:
                continue

            term_tf = count / total
            term_idf = self.idf[term]
            input_tfidf[term] = term_tf * term_idf

        return input_tfidf

    def get_cluster_tfidf_vectors(self):
        # Obtain frequency vectors
        freq_vectors = {}
        for cluster, phrases in self.cluster_text.items():
            raw_text = ' '.join(phrases)
            tokens = clean_text(raw_text)
            freq_vector = convert_to_frequency(tokens)
            freq_vectors[cluster] = freq_vector

        # Obtain TF-IDF vectors
        tfidf = TfidfConverter(freq_vectors)
        tfidf.generate_tfidf_vectors()
        self.cluster_tfidf = tfidf.tfidf_vectors
        self.idf = tfidf.idf
