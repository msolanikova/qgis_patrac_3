def set_progress(progress_bar, value):
    """Sets a QProgressBar from a QgsTask progress value: the task reports a float, QProgressBar.setValue needs an int."""
    progress_bar.setValue(int(value))
