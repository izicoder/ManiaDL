namespace ManiaDL.Core.Progress;

public sealed record TaskItem(int Id, string Description, double Completed, double? Total);

public sealed record ProgressSnapshot(string Message, IReadOnlyList<TaskItem> Tasks);

/// <summary>
/// Thread-safe progress board. The downloader needs add/update/remove; the host
/// snapshots it at most every 120 ms and forwards the snapshot to the UI.
/// </summary>
public sealed class TaskBoard
{
    private readonly object _lock = new();
    private readonly SortedDictionary<int, TaskItem> _tasks = new();
    private int _next = 1;
    private string _message = "";

    public void Reset()
    {
        lock (_lock)
        {
            _tasks.Clear();
            _next = 1;
            _message = "";
        }
    }

    public int AddTask(string description, double? total = null)
    {
        lock (_lock)
        {
            var id = _next++;
            _tasks[id] = new TaskItem(id, description, 0.0, total);
            return id;
        }
    }

    public void Update(int id, double? completed = null, double? total = null,
        double? advance = null, string? description = null)
    {
        lock (_lock)
        {
            if (!_tasks.TryGetValue(id, out var task))
            {
                return;
            }

            _tasks[id] = task with
            {
                Description = description ?? task.Description,
                Total = total ?? task.Total,
                Completed = completed ?? (advance is { } step ? task.Completed + step : task.Completed),
            };
        }
    }

    public void RemoveTask(int id)
    {
        lock (_lock)
        {
            _tasks.Remove(id);
        }
    }

    public void SetMessage(string message)
    {
        lock (_lock)
        {
            _message = message;
        }
    }

    public ProgressSnapshot Snapshot()
    {
        lock (_lock)
        {
            return new ProgressSnapshot(_message, _tasks.Values.ToArray());
        }
    }
}
