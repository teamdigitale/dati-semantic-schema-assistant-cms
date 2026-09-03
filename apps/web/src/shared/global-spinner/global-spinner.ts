import { Component } from '@angular/core';
import { GlobalLoader } from '../services/global-loader';

@Component({
  selector: 'app-global-spinner',
  standalone: false,
  templateUrl: './global-spinner.html',
  styleUrl: './global-spinner.css'
})
export class GlobalSpinner {
  constructor(public loader: GlobalLoader) {}

}
