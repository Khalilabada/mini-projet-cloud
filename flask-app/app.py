from flask import Flask, request, jsonify
import psycopg2, os, redis, json, time
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
metrics = PrometheusMetrics(app)

cache = redis.Redis(
    host=os.environ.get('REDIS_HOST', 'redis'),
    port=6379,
    decode_responses=True
)

def get_db():
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id SERIAL PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        done BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    cur.close()
    conn.close()

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200

@app.route('/tasks', methods=['GET'])
def get_tasks():
    cached = cache.get('tasks_list')
    if cached:
        return jsonify(json.loads(cached))
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, title, done FROM tasks')
    tasks = [{'id': r[0], 'title': r[1], 'done': r[2]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    cache.setex('tasks_list', 60, json.dumps(tasks))
    return jsonify(tasks)

@app.route('/tasks', methods=['POST'])
def create_task():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT INTO tasks (title) VALUES (%s) RETURNING id', (data['title'],))
    conn.commit()
    task_id = cur.fetchone()[0]
    cur.close()
    conn.close()
    cache.delete('tasks_list')
    return jsonify({'id': task_id}), 201

@app.route('/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM tasks WHERE id = %s', (task_id,))
    conn.commit()
    cur.close()
    conn.close()
    cache.delete('tasks_list')
    return jsonify({'message': 'Task deleted'}), 200

@app.route('/visits')
def visits():
    count = cache.incr('visit_counter')
    return jsonify({'visits': count})

if __name__ == '__main__':
    for _ in range(10):
        try:
            init_db()
            break
        except Exception as e:
            print(f"DB not ready: {e}")
            time.sleep(3)
    app.run(host='0.0.0.0', port=5000)