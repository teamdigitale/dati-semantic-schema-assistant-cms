import { Component } from '@angular/core';
import { Loader } from '../services/loader';

@Component({
  selector: 'app-spinner',
  templateUrl: './spinner.html',
  styleUrls: ['./spinner.css'],
  standalone: false
})
export class Spinner {
  constructor(public loader: Loader) {}
}
